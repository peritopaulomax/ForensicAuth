"""SAFE (KDD'25) — single-image synthetic detection inference."""

from __future__ import annotations

import importlib.util
import logging
from typing import Callable

import torch
import torch.nn.functional as F
from PIL import Image
from torchvision import transforms
from torchvision.transforms import InterpolationMode

from core.gpu_inference import (
    device_display_label,
    release_gpu_memory,
    resolve_inference_device,
    run_with_device_fallback,
)
from core.legacy.effort.effort_pipeline import effort_row
from core.legacy.safe.safe_runtime import resolve_checkpoint, safe_runtime_status, safe_vendor_dir

logger = logging.getLogger(__name__)

ProgressFn = Callable[[int, str], None] | None

INPUT_SIZE = 256
MODEL_LABEL = "SAFE (KDD'25)"

_model_cache: dict[str, torch.nn.Module] = {}


def _report(on_progress: ProgressFn, pct: int, label: str) -> None:
    if on_progress:
        on_progress(pct, label)


def _load_safe_resnet50():
    """Carrega resnet50 do vendor sem colidir com o pacote backend `models`."""
    module_path = safe_vendor_dir() / "models" / "resnet.py"
    if not module_path.is_file():
        raise RuntimeError(f"SAFE resnet.py ausente em {module_path}")
    spec = importlib.util.spec_from_file_location("safe_vendor_resnet", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Nao foi possivel carregar {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    factory = getattr(module, "resnet50", None)
    if factory is None:
        raise RuntimeError("SAFE resnet50 nao encontrado no vendor")
    return factory


def _eval_transform() -> transforms.Compose:
    """Resize 256x256 — compativel com eval crop para imagens forenses de tamanho arbitrario."""
    return transforms.Compose(
        [
            transforms.Resize(
                (INPUT_SIZE, INPUT_SIZE),
                interpolation=InterpolationMode.BILINEAR,
            ),
            transforms.ToTensor(),
        ]
    )


def _load_model(device: torch.device) -> torch.nn.Module:
    cache_key = device.type
    if cache_key in _model_cache:
        return _model_cache[cache_key]

    ckpt_path = resolve_checkpoint()
    if ckpt_path is None:
        raise RuntimeError("Checkpoint SAFE ausente")

    resnet50 = _load_safe_resnet50()
    model = resnet50(num_classes=2)
    try:
        obj = torch.load(str(ckpt_path), map_location="cpu", weights_only=False)
    except TypeError:
        obj = torch.load(str(ckpt_path), map_location="cpu")

    state = obj.get("model", obj) if isinstance(obj, dict) else obj
    if isinstance(state, dict):
        state = {k.replace("module.", ""): v for k, v in state.items()}
    model.load_state_dict(state, strict=True)
    model = model.to(device)
    model.eval()
    _model_cache[cache_key] = model
    return model


def clear_safe_model_cache() -> None:
    for model in list(_model_cache.values()):
        release_gpu_memory(model)
    _model_cache.clear()
    release_gpu_memory()


def safe_model_cache_keys() -> list[str]:
    return list(_model_cache.keys())


def infer_safe_from_pil(image: Image.Image, device: torch.device) -> float:
    """Retorna probabilidade de imagem sintetica (classe fake=1)."""
    model = _load_model(device)
    tensor = _eval_transform()(image.convert("RGB")).unsqueeze(0).to(device)
    with torch.no_grad():
        logits = model(tensor)
        prob_fake = F.softmax(logits, dim=1)[0, 1].item()
    return float(prob_fake)


def predict_safe_row(
    image: Image.Image,
    on_progress: ProgressFn = None,
) -> list[str] | None:
    """Uma linha SAFE para a tabela de detecção de imagens sinteticas."""
    ok, reason = safe_runtime_status()
    if not ok:
        logger.debug("SAFE indisponivel: %s", reason)
        return None

    preferred = resolve_inference_device()
    pct = 62
    _report(on_progress, pct, f"Inferindo {MODEL_LABEL} em {device_display_label(preferred)}…")

    def _run(dev: torch.device):
        return infer_safe_from_pil(image, dev)

    def _on_cpu_fallback(exc_reason: str) -> None:
        _report(on_progress, pct, f"{MODEL_LABEL} em CPU — fallback VRAM…")

    try:
        prob, device = run_with_device_fallback(
            _run,
            on_fallback=clear_safe_model_cache,
            on_before_cpu_fallback=_on_cpu_fallback,
        )
    except Exception as exc:
        logger.warning("SAFE falhou: %s", exc)
        return None

    return effort_row(MODEL_LABEL, prob, inference_device=device.type)


def warm_safe_model(*, device: torch.device | None = None) -> bool:
    """Pre-carrega SAFE e executa forward dummy (mantem em cache)."""
    ok, _ = safe_runtime_status()
    if not ok:
        return False
    target = device or resolve_inference_device()
    model = _load_model(target)
    dummy = torch.zeros(1, 3, INPUT_SIZE, INPUT_SIZE, device=target)
    with torch.no_grad():
        model(dummy)
    return True
