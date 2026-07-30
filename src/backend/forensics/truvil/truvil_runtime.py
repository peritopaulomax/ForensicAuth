"""Runtime paths and availability for TruVIL (video inpainting localization)."""

from __future__ import annotations

import os
from pathlib import Path

from forensics.paths import workspace_root

MODEL_LABEL = "TruVIL (video inpainting localization)"
TECHNIQUE_NAME = "truvil"
DEFAULT_CLIP_LEN = 5
DEFAULT_HEIGHT = 240
DEFAULT_WIDTH = 432
DEFAULT_SAMPLE_EVERY = 5
DEFAULT_MAX_CLIPS = 24
WEIGHT_FILE = "TruVIL_train_VI_OP.pth"
GDRIVE_FILE_ID = "1eIttOWmFopKKGFyEN5yaUJfdZeg2nfDu"


def truvil_vendor_dir() -> Path:
    return workspace_root() / "vendor" / "truvil"


def truvil_models_dir() -> Path:
    env = os.environ.get("TRUVIL_MODELS_DIR")
    if env:
        return Path(env).resolve()
    from app.config import get_settings

    return (Path(get_settings().MODELS_DIR) / "truvil").resolve()


def truvil_weights_dir() -> Path:
    return truvil_models_dir() / "weights"


def weight_path() -> Path:
    custom = os.environ.get("TRUVIL_WEIGHTS_PATH")
    if custom:
        return Path(custom).resolve()
    return truvil_weights_dir() / WEIGHT_FILE


def _package_ok() -> tuple[bool, str]:
    missing: list[str] = []
    for module in ("torch", "timm", "cv2", "numpy", "PIL", "mmengine"):
        try:
            __import__(module if module != "PIL" else "PIL")
        except ImportError:
            missing.append(module)
    if missing:
        return False, f"Dependencias ausentes para TruVIL: {', '.join(missing)}"
    return True, ""


def truvil_runtime_status() -> tuple[bool, str]:
    vendor = truvil_vendor_dir()
    if not vendor.is_dir():
        return False, f"Vendor TruVIL ausente em {vendor} (git clone https://github.com/multimediaFor/TruVIL)"

    ok_pkg, pkg_reason = _package_ok()
    if not ok_pkg:
        return False, pkg_reason

    w = weight_path()
    if w.is_file() and w.stat().st_size > 1_000_000:
        return True, ""

    return (
        False,
        "Checkpoint TruVIL ausente. "
        f"Execute: python scripts/download_truvil_weights.py "
        f"ou coloque o .pth em {w} / defina TRUVIL_WEIGHTS_PATH. "
        f"(Google Drive id={GDRIVE_FILE_ID})",
    )
