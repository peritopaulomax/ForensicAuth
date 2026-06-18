"""CAMO (BitMind) — Content-Aware Model Orchestration for synthetic/deepfake detection."""

from __future__ import annotations

import logging
import sys
from typing import Callable

import numpy as np
import torch
from PIL import Image

from core.gpu_inference import (
    device_display_label,
    release_gpu_memory,
    resolve_inference_device,
    run_with_device_fallback,
)
from core.legacy.camo.camo_runtime import MODEL_LABEL, camo_runtime_status, camo_vendor_dir
from core.legacy.camo.camo_vendor import bootstrap_camo_modules, camo_vendor_context
from core.legacy.effort.effort_pipeline import effort_row

logger = logging.getLogger(__name__)

ProgressFn = Callable[[int, str], None] | None

_detector_cache: dict[str, object] = {}


def _report(on_progress: ProgressFn, pct: int, label: str) -> None:
    if on_progress:
        on_progress(pct, label)


def clear_camo_model_cache() -> None:
    for detector in list(_detector_cache.values()):
        try:
            free = getattr(detector, "free_memory", None)
            if callable(free):
                free()
            else:
                release_gpu_memory(detector)
        except Exception:
            pass
    _detector_cache.clear()
    release_gpu_memory()


def camo_model_cache_keys() -> list[str]:
    return list(_detector_cache.keys())


def _load_detector(device: torch.device):
    cache_key = device.type
    if cache_key in _detector_cache:
        return _detector_cache[cache_key]

    with camo_vendor_context():
        bootstrap_camo_modules(camo_vendor_dir())
        CAMOImageDetector = sys.modules[
            "base_miner.deepfake_detectors.camo_detector"
        ].CAMOImageDetector
        device_label = "cuda" if device.type == "cuda" else "cpu"
        detector = CAMOImageDetector(device=device_label)

    _detector_cache[cache_key] = detector
    return detector


def infer_camo_from_pil(image: Image.Image, device: torch.device) -> float:
    """Probabilidade de imagem sintetica/fake via CAMO (max dos experts UCF)."""
    detector = _load_detector(device)
    with camo_vendor_context():
        prob = detector(image.convert("RGB"))
    return float(np.asarray(prob, dtype=np.float64).reshape(-1)[0])


def predict_camo_row(
    image: Image.Image,
    on_progress: ProgressFn = None,
) -> list[str] | None:
    """Uma linha CAMO para a tabela de detecção de imagens sinteticas."""
    ok, reason = camo_runtime_status()
    if not ok:
        logger.debug("CAMO indisponivel: %s", reason)
        return None

    preferred = resolve_inference_device()
    pct = 63
    _report(on_progress, pct, f"Inferindo {MODEL_LABEL} em {device_display_label(preferred)}…")

    def _run(dev: torch.device):
        return infer_camo_from_pil(image, dev)

    def _on_cpu_fallback(_exc_reason: str) -> None:
        _report(on_progress, pct, f"{MODEL_LABEL} em CPU — fallback VRAM…")

    try:
        prob, device = run_with_device_fallback(
            _run,
            on_fallback=clear_camo_model_cache,
            on_before_cpu_fallback=_on_cpu_fallback,
        )
    except Exception as exc:
        logger.warning("CAMO falhou: %s", exc)
        return None

    return effort_row(MODEL_LABEL, prob, inference_device=device.type)


def warm_camo_model(*, device: torch.device | None = None) -> bool:
    ok, _ = camo_runtime_status()
    if not ok:
        return False
    target = device or resolve_inference_device()
    dummy = Image.new("RGB", (256, 256), color=(100, 120, 140))
    try:
        infer_camo_from_pil(dummy, target)
        return True
    except Exception as exc:
        logger.warning("CAMO warmup falhou: %s", exc)
        return False
