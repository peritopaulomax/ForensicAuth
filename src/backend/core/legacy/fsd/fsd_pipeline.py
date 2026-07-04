"""Official Forensic Self-Descriptions inference wrapper."""

from __future__ import annotations

import logging
import sys
from contextlib import suppress
from contextlib import contextmanager
from typing import Callable

import torch
from PIL import Image

from core.gpu_inference import device_display_label, release_gpu_memory, resolve_inference_device, run_with_device_fallback
from core.legacy.fsd.fsd_runtime import fsd_runtime_status, fsd_vendor_dir, fsd_weights_dir

logger = logging.getLogger(__name__)

ProgressFn = Callable[[int, str], None] | None
MODEL_LABEL = "FSD (CVPR 2025)"

_cache: dict[str, object] = {}


@contextmanager
def _fsd_vendor_context():
    vendor = str(fsd_vendor_dir())
    inserted = vendor not in sys.path
    if inserted:
        sys.path.insert(0, vendor)
    try:
        yield
    finally:
        if inserted:
            with suppress(ValueError):
                sys.path.remove(vendor)


def clear_fsd_model_cache() -> None:
    for detector in list(_cache.values()):
        release_gpu_memory(getattr(detector, "fre", None))
    _cache.clear()
    release_gpu_memory()


def _load_detector(device: torch.device):
    key = device.type
    if key in _cache:
        return _cache[key]
    with _fsd_vendor_context():
        from fsd import FSDDetector

        detector = FSDDetector.load(weights_dir=fsd_weights_dir(), device=device.type)
    _cache[key] = detector
    return detector


def infer_fsd_from_pil(image: Image.Image, device: torch.device):
    detector = _load_detector(device)
    return detector.score(image.convert("RGB"))


def predict_fsd_row(image: Image.Image, on_progress: ProgressFn = None) -> list[str] | None:
    ok, reason = fsd_runtime_status()
    if not ok:
        logger.debug("FSD indisponivel: %s", reason)
        return None

    preferred = resolve_inference_device()
    if on_progress:
        on_progress(66, f"Inferindo {MODEL_LABEL} em {device_display_label(preferred)}...")

    def _run(dev: torch.device):
        return infer_fsd_from_pil(image, dev)

    try:
        result, device = run_with_device_fallback(
            _run,
            on_fallback=clear_fsd_model_cache,
            on_before_cpu_fallback=lambda _reason: on_progress and on_progress(66, f"{MODEL_LABEL} em CPU - fallback VRAM..."),
        )
    except Exception as exc:
        logger.warning("FSD falhou: %s", exc)
        return None

    decision = "AI" if bool(result.is_fake) else "REAL"
    return [
        MODEL_LABEL,
        f"{float(result.z_score):.4f}",
        "N/A",
        f"limiar={float(result.threshold):.2f}",
        decision,
        device_display_label(device.type),
    ]

