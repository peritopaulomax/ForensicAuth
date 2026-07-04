"""DeeCLIP official single-image synthetic detection inference."""

from __future__ import annotations

import logging
import math
from typing import Callable

import torch
from PIL import Image

from core.gpu_inference import (
    device_display_label,
    release_gpu_memory,
    resolve_inference_device,
    run_with_device_fallback,
)
from core.legacy.deeclip.deeclip_runtime import (
    CLIP_MODEL_ID,
    deeclip_runtime_status,
    resolve_checkpoint,
    resolve_clip_snapshot_path,
)
from core.legacy.deeclip.deeclip_vendor import load_deeclip_class

logger = logging.getLogger(__name__)

ProgressFn = Callable[[int, str], None] | None

MODEL_LABEL = "DeeCLIP (CLIP ViT-L/14)"
LAYER_INDICES = [1, 3, 5, 8, 10, 13, 15, 17, 19, 21, 22, 23]

_model_cache: dict[str, torch.nn.Module] = {}
_processor_cache: object | None = None


def _report(on_progress: ProgressFn, pct: int, label: str) -> None:
    if on_progress:
        on_progress(pct, label)


def _load_processor():
    global _processor_cache

    if _processor_cache is not None:
        return _processor_cache
    from transformers import CLIPImageProcessor

    clip_path = resolve_clip_snapshot_path()
    if clip_path is None:
        raise RuntimeError(f"Cache HuggingFace ausente para {CLIP_MODEL_ID}")
    _processor_cache = CLIPImageProcessor.from_pretrained(str(clip_path), local_files_only=True)
    return _processor_cache


def _load_model(device: torch.device) -> torch.nn.Module:
    cache_key = device.type
    if cache_key in _model_cache:
        return _model_cache[cache_key]

    clip_path = resolve_clip_snapshot_path()
    ckpt_path = resolve_checkpoint()
    if clip_path is None:
        raise RuntimeError(f"Cache HuggingFace ausente para {CLIP_MODEL_ID}")
    if ckpt_path is None:
        raise RuntimeError("Checkpoint DeeCLIP ausente")

    deeclip_cls = load_deeclip_class()
    model = deeclip_cls(model_name=str(clip_path), layer_indices=LAYER_INDICES).to(device)
    try:
        state = torch.load(str(ckpt_path), map_location=device, weights_only=False)
    except TypeError:
        state = torch.load(str(ckpt_path), map_location=device)
    model.load_state_dict(state, strict=False)
    model.eval()
    _model_cache[cache_key] = model
    return model


def clear_deeclip_model_cache() -> None:
    global _processor_cache

    for model in list(_model_cache.values()):
        release_gpu_memory(model)
    _model_cache.clear()
    _processor_cache = None
    release_gpu_memory()


def deeclip_model_cache_keys() -> list[str]:
    return list(_model_cache.keys())


def infer_deeclip_from_pil(image: Image.Image, device: torch.device) -> float:
    """Return DeeCLIP's official sigmoid probability for the synthetic/fake class."""
    model = _load_model(device)
    processor = _load_processor()
    tensor = processor(images=image.convert("RGB"), return_tensors="pt")["pixel_values"].to(device)
    with torch.no_grad():
        _, _, outputs = model(tensor, train=False)
        prob_fake = torch.sigmoid(outputs).float().detach().cpu().reshape(-1)[0].item()
    return float(prob_fake)


def predict_deeclip_row(
    image: Image.Image,
    on_progress: ProgressFn = None,
) -> list[str] | None:
    """A DeeCLIP row for the synthetic image detection table."""
    ok, reason = deeclip_runtime_status()
    if not ok:
        logger.debug("DeeCLIP indisponivel: %s", reason)
        return None

    preferred = resolve_inference_device()
    pct = 65
    _report(on_progress, pct, f"Inferindo {MODEL_LABEL} em {device_display_label(preferred)}...")

    def _run(dev: torch.device):
        return infer_deeclip_from_pil(image, dev)

    def _on_cpu_fallback(exc_reason: str) -> None:
        _report(on_progress, pct, f"{MODEL_LABEL} em CPU - fallback VRAM...")

    try:
        prob, device = run_with_device_fallback(
            _run,
            on_fallback=clear_deeclip_model_cache,
            on_before_cpu_fallback=_on_cpu_fallback,
        )
    except Exception as exc:
        logger.warning("DeeCLIP falhou: %s", exc)
        return None

    ai_score = min(1.0 - 1e-9, max(1e-9, float(prob)))
    real_score = 1.0 - ai_score
    ratio = real_score / ai_score
    decision = "AI" if ai_score > 0.5 else "REAL"
    return [
        MODEL_LABEL,
        f"{ai_score:.4f}",
        f"{real_score:.4f}",
        f"{math.log10(ratio):.2f}" if math.isfinite(ratio) else "inf",
        decision,
        device_display_label(device.type),
    ]
