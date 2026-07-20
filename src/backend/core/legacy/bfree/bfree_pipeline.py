"""B-Free inference wrapper for synthetic image detection."""

from __future__ import annotations

import logging
import math
import sys
from contextlib import contextmanager, suppress
from importlib import util as importlib_util
from typing import Callable

import torch
import numpy as np
from PIL import Image
from torchvision.transforms import Compose

from core.gpu_inference import device_display_label, release_gpu_memory, resolve_inference_device, run_with_device_fallback
from core.legacy.bfree.bfree_runtime import (
    MODEL_NAME,
    bfree_config_path,
    bfree_runtime_status,
    bfree_vendor_dir,
    bfree_weights_dir,
)

logger = logging.getLogger(__name__)

ProgressFn = Callable[[int, str], None] | None
MODEL_LABEL = "B-Free (Bias-free synthetic image detector)"

_cache: dict[str, tuple[torch.nn.Module, Compose]] = {}


@contextmanager
def _bfree_vendor_context():
    vendor = str(bfree_vendor_dir())
    inserted = vendor not in sys.path
    if inserted:
        sys.path.insert(0, vendor)
    try:
        yield
    finally:
        if inserted:
            with suppress(ValueError):
                sys.path.remove(vendor)


def _clear_vendor_imports() -> None:
    for key in list(sys.modules):
        if key in {"networks", "utils"} or key.startswith(("networks.", "utils.")):
            sys.modules.pop(key, None)


def clear_bfree_model_cache() -> None:
    release_gpu_memory(*(model for model, _transform in _cache.values()))
    _cache.clear()
    release_gpu_memory()


def _sigmoid(score: float) -> float:
    if score >= 0:
        z = math.exp(-score)
        return 1.0 / (1.0 + z)
    z = math.exp(score)
    return z / (1.0 + z)


def _load_model(device: torch.device) -> tuple[torch.nn.Module, Compose]:
    key = device.type
    if key in _cache:
        return _cache[key]

    _clear_vendor_imports()
    with _bfree_vendor_context():
        import yaml
        from networks import get_network, load_weights

        with open(bfree_config_path(MODEL_NAME), encoding="utf-8") as fh:
            config = yaml.load(fh, Loader=yaml.FullLoader)
        if config.get("model_name") != MODEL_NAME or config.get("patch_size") is not None:
            raise RuntimeError(f"Config B-Free inesperada: {config}")

        model = get_network(config["arch"])
        model = load_weights(model, str(bfree_weights_dir() / MODEL_NAME / config["weights_file"]))
        model = model.to(device).eval()
        transform = Compose(_load_normalization_module().get_list_norm(config["norm_type"]))

    _cache[key] = (model, transform)
    return model, transform


def _load_normalization_module():
    path = bfree_vendor_dir() / "utils" / "normalization.py"
    spec = importlib_util.spec_from_file_location("bfree_normalization", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {path}")
    module = importlib_util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def infer_bfree_from_pil(
    image: Image.Image,
    device: torch.device,
    *,
    return_embedding: bool = False,
) -> float | tuple[float, np.ndarray]:
    from core.legacy.synthetic_image_detection.embedding_utils import (
        flatten_embedding,
        register_fc_input_hook,
    )

    model, transform = _load_model(device)
    tensor = transform(image.convert("RGB")).unsqueeze(0).to(device)
    timm_model = getattr(model, "model", model)
    head = getattr(timm_model, "head", None)
    handle = None
    store: list[torch.Tensor] | None = None
    if return_embedding:
        if head is None:
            raise RuntimeError("Could not locate B-Free classification head for embedding hook")
        handle, store = register_fc_input_hook(head)
    try:
        with torch.no_grad():
            output = model(tensor).detach().cpu().numpy()
        score = float(output.reshape(-1)[0])
        if return_embedding:
            if not store:
                raise RuntimeError("B-Free embedding hook did not capture any activation")
            crop_embeddings = store[0]
            if crop_embeddings.dim() == 1:
                crop_embeddings = crop_embeddings.unsqueeze(0)
            emb = flatten_embedding(crop_embeddings.mean(dim=0, keepdim=True))
            return score, emb
    finally:
        if handle is not None:
            handle.remove()
    return score


def predict_bfree_row(image: Image.Image, on_progress: ProgressFn = None) -> list[str] | None:
    ok, reason = bfree_runtime_status()
    if not ok:
        logger.debug("B-Free indisponivel: %s", reason)
        return None

    preferred = resolve_inference_device()
    if on_progress:
        on_progress(52, f"Inferindo {MODEL_LABEL} em {device_display_label(preferred)}...")

    def _run(dev: torch.device):
        return infer_bfree_from_pil(image, dev)

    try:
        score, device = run_with_device_fallback(
            _run,
            on_fallback=clear_bfree_model_cache,
            on_before_cpu_fallback=lambda _reason: on_progress
            and on_progress(52, f"{MODEL_LABEL} em CPU - fallback VRAM..."),
        )
    except Exception as exc:
        logger.warning("B-Free falhou: %s", exc)
        return None

    fake_score = _sigmoid(score)
    real_score = 1.0 - fake_score
    decision = "AI" if score > 0 else "REAL"
    return [
        MODEL_LABEL,
        f"{fake_score:.4f}",
        f"{real_score:.4f}",
        f"score={score:.4f}",
        decision,
        device_display_label(device.type),
    ]
