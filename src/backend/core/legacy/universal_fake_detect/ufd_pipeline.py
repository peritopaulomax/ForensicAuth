"""Official UniversalFakeDetect inference wrapper."""

from __future__ import annotations

import logging
import math
import sys
from contextlib import contextmanager, suppress
from typing import Callable

import torch
from PIL import Image
from torchvision import transforms

from core.gpu_inference import device_display_label, release_gpu_memory, resolve_inference_device, run_with_device_fallback
from core.legacy.universal_fake_detect.ufd_runtime import (
    ufd_clip_cache_dir,
    ufd_runtime_status,
    ufd_vendor_dir,
    ufd_weights_path,
)

logger = logging.getLogger(__name__)

ProgressFn = Callable[[int, str], None] | None
MODEL_LABEL = "UniversalFakeDetect (CLIP ViT-L/14)"

_cache: dict[str, torch.nn.Module] = {}

_transform = transforms.Compose(
    [
        transforms.CenterCrop(224),
        transforms.ToTensor(),
        transforms.Normalize(
            mean=[0.48145466, 0.4578275, 0.40821073],
            std=[0.26862954, 0.26130258, 0.27577711],
        ),
    ]
)


@contextmanager
def _ufd_vendor_context():
    vendor = str(ufd_vendor_dir())
    inserted = vendor not in sys.path
    if inserted:
        sys.path.insert(0, vendor)
    try:
        yield
    finally:
        if inserted:
            with suppress(ValueError):
                sys.path.remove(vendor)


def _patch_pkg_resources_for_legacy_clip() -> None:
    try:
        import pkg_resources
        from packaging import version as packaging_version

        if not hasattr(pkg_resources, "packaging"):
            pkg_resources.packaging = type("PackagingCompat", (), {"version": packaging_version})
    except Exception:
        pass


def _clear_vendor_imports() -> None:
    for key in list(sys.modules):
        if key in {"models", "networks", "options", "data"} or key.startswith(("models.", "networks.", "options.", "data.")):
            sys.modules.pop(key, None)


@contextmanager
def _isolated_vendor_modules(*prefixes: str):
    saved = {
        key: value
        for key, value in sys.modules.items()
        if key in prefixes or any(key.startswith(f"{prefix}.") for prefix in prefixes)
    }
    for key in list(saved):
        sys.modules.pop(key, None)
    try:
        yield
    finally:
        for key in list(sys.modules):
            if key in prefixes or any(key.startswith(f"{prefix}.") for prefix in prefixes):
                sys.modules.pop(key, None)
        sys.modules.update(saved)


def clear_ufd_model_cache() -> None:
    release_gpu_memory(*list(_cache.values()))
    _cache.clear()
    release_gpu_memory()


def _load_model(device: torch.device) -> torch.nn.Module:
    key = device.type
    if key in _cache:
        return _cache[key]
    _patch_pkg_resources_for_legacy_clip()
    with _isolated_vendor_modules("models", "networks", "options", "data"), _ufd_vendor_context():
        from models import get_model
        from models.clip import clip as vendor_clip

        original_load = vendor_clip.load

        def load_from_project_cache(name, device="cpu", jit=False, download_root=None):
            return original_load(
                name,
                device=device,
                jit=jit,
                download_root=download_root or str(ufd_clip_cache_dir()),
            )

        vendor_clip.load = load_from_project_cache
        model = get_model("CLIP:ViT-L/14")
        state = torch.load(str(ufd_weights_path()), map_location="cpu", weights_only=False)
        model.fc.load_state_dict(state)
        model.eval().to(device)
    _cache[key] = model
    return model


def infer_ufd_from_pil(image: Image.Image, device: torch.device) -> float:
    model = _load_model(device)
    tensor = _transform(image.convert("RGB")).unsqueeze(0).to(device)
    with torch.no_grad():
        return float(torch.sigmoid(model(tensor)).flatten()[0].detach().cpu().item())


def predict_ufd_row(image: Image.Image, on_progress: ProgressFn = None) -> list[str] | None:
    ok, reason = ufd_runtime_status()
    if not ok:
        logger.debug("UniversalFakeDetect indisponivel: %s", reason)
        return None

    preferred = resolve_inference_device()
    if on_progress:
        on_progress(66, f"Inferindo {MODEL_LABEL} em {device_display_label(preferred)}...")

    def _run(dev: torch.device):
        return infer_ufd_from_pil(image, dev)

    try:
        prob, device = run_with_device_fallback(
            _run,
            on_fallback=clear_ufd_model_cache,
            on_before_cpu_fallback=lambda _reason: on_progress and on_progress(66, f"{MODEL_LABEL} em CPU - fallback VRAM..."),
        )
    except Exception as exc:
        logger.warning("UniversalFakeDetect falhou: %s", exc)
        return None

    real_score = 1.0 - prob
    ratio = real_score / prob if prob > 1e-9 else float("inf")
    decision = "AI" if prob > 0.5 else "REAL"
    return [
        MODEL_LABEL,
        f"{prob:.4f}",
        f"{real_score:.4f}",
        f"{math.log10(ratio):.2f}",
        decision,
        device_display_label(device.type),
    ]

