"""Runtime paths and availability for ViLocal (video inpainting localization)."""

from __future__ import annotations

import os
from pathlib import Path

from forensics.paths import workspace_root

MODEL_LABEL = "ViLocal (video inpainting localization)"
TECHNIQUE_NAME = "vilocal"
DEFAULT_CLIP_LEN = 5
DEFAULT_HEIGHT = 240
DEFAULT_WIDTH = 432
DEFAULT_SAMPLE_EVERY = 5
DEFAULT_MAX_CLIPS = 24
WEIGHT_FILE = "train_VI_OP.pth"


def vilocal_vendor_dir() -> Path:
    # Código de inferência vive em train_stage2/
    return workspace_root() / "vendor" / "vilocal" / "train_stage2"


def vilocal_models_dir() -> Path:
    env = os.environ.get("VILOCAL_MODELS_DIR")
    if env:
        return Path(env).resolve()
    from app.config import get_settings

    return (Path(get_settings().MODELS_DIR) / "vilocal").resolve()


def vilocal_weights_dir() -> Path:
    return vilocal_models_dir() / "weights"


def weight_path() -> Path:
    custom = os.environ.get("VILOCAL_WEIGHTS_PATH")
    if custom:
        return Path(custom).resolve()
    primary = vilocal_weights_dir() / WEIGHT_FILE
    if primary.is_file():
        return primary
    # Fallback: pesos versionados no vendor clone
    vendor_w = vilocal_vendor_dir() / "weights" / WEIGHT_FILE
    return vendor_w


def _package_ok() -> tuple[bool, str]:
    missing: list[str] = []
    for module in ("torch", "timm", "cv2", "numpy", "PIL", "mmengine"):
        try:
            __import__(module if module != "PIL" else "PIL")
        except ImportError:
            missing.append(module)
    if missing:
        return False, f"Dependencias ausentes para ViLocal: {', '.join(missing)}"
    return True, ""


def vilocal_runtime_status() -> tuple[bool, str]:
    vendor = vilocal_vendor_dir()
    if not vendor.is_dir():
        return (
            False,
            f"Vendor ViLocal ausente em {vendor} "
            "(git clone https://github.com/multimediaFor/ViLocal vendor/vilocal)",
        )

    ok_pkg, pkg_reason = _package_ok()
    if not ok_pkg:
        return False, pkg_reason

    w = weight_path()
    if w.is_file() and w.stat().st_size > 1_000_000:
        return True, ""

    return (
        False,
        "Checkpoint ViLocal ausente. "
        f"Execute: python scripts/download_vilocal_weights.py "
        f"ou coloque {WEIGHT_FILE} em {vilocal_weights_dir()} / defina VILOCAL_WEIGHTS_PATH. "
        "Fonte: https://github.com/multimediaFor/ViLocal",
    )
