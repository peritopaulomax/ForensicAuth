"""Runtime for Low-Resolution Fake Video Detection (TUM / lukasHoel)."""

from __future__ import annotations

import os
from pathlib import Path

MODEL_LABEL = "Low-Res Fake Video (TUM)"
TECHNIQUE_NAME = "lowres_fake_video"
THRESHOLD = 0.5
DEFAULT_WEIGHT = "baseline_xception.pt"

GDRIVE_FOLDER = "1m_XR1HWRMkXv-pS2bUxo3hEHsMeJ3fxN"


def _workspace_root() -> Path:
    return Path(__file__).resolve().parents[5]


def lfv_vendor_dir() -> Path:
    return _workspace_root() / "vendor" / "fake-video-detection"


def lfv_models_dir() -> Path:
    env = os.environ.get("LFV_MODELS_DIR")
    if env:
        return Path(env).resolve()
    from app.config import get_settings

    return (Path(get_settings().MODELS_DIR) / "lowres_fake_video").resolve()


def lfv_weights_dir() -> Path:
    return lfv_models_dir() / "weights"


def weight_path() -> Path:
    custom = os.environ.get("LFV_WEIGHTS_PATH")
    if custom:
        return Path(custom).resolve()
    return lfv_weights_dir() / DEFAULT_WEIGHT


def _package_ok() -> tuple[bool, str]:
    missing: list[str] = []
    for module in ("torch", "torchvision", "cv2", "decord", "numpy"):
        try:
            __import__(module)
        except ImportError:
            missing.append(module)
    return (False, f"Dependencias ausentes: {', '.join(missing)}") if missing else (True, "")


def lfv_runtime_status() -> tuple[bool, str]:
    vendor = lfv_vendor_dir()
    if not vendor.is_dir():
        return False, f"Vendor fake-video-detection ausente em {vendor}"
    ok_pkg, reason = _package_ok()
    if not ok_pkg:
        return False, reason
    w = weight_path()
    if not w.is_file() or w.stat().st_size < 10_000:
        return (
            False,
            "Peso ausente. Execute: python scripts/download_lfv_weights.py "
            "(o README do repo aponta Google Drive, nao GitHub; usamos fallback DeepfakeBench se Drive falhar).",
        )
    return True, ""
