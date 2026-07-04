"""Runtime paths and availability for UniversalFakeDetect."""

from __future__ import annotations

import os
from pathlib import Path


def _workspace_root() -> Path:
    return Path(__file__).resolve().parents[5]


def _models_dir() -> Path:
    from app.config import get_settings

    return Path(get_settings().MODELS_DIR)


def ufd_vendor_dir() -> Path:
    env = os.environ.get("UFD_VENDOR_DIR")
    if env:
        return Path(env).resolve()
    return _workspace_root() / "vendor" / "universal_fake_detect"


def ufd_weights_path() -> Path:
    env = os.environ.get("UFD_WEIGHTS_PATH")
    if env:
        return Path(env).resolve()
    return (_models_dir() / "universal_fake_detect" / "fc_weights.pth").resolve()


def ufd_clip_cache_dir() -> Path:
    env = os.environ.get("UFD_CLIP_CACHE_DIR")
    if env:
        return Path(env).resolve()
    return (_models_dir() / "universal_fake_detect" / "clip").resolve()


def ufd_runtime_status() -> tuple[bool, str]:
    vendor = ufd_vendor_dir()
    if not (vendor / "models" / "clip_models.py").is_file():
        return False, f"Codigo UniversalFakeDetect ausente em {vendor}"
    weights = ufd_weights_path()
    if not weights.is_file() or weights.stat().st_size < 100:
        return False, f"Pesos UniversalFakeDetect ausentes em {weights}. Execute: python scripts/download_ufd_assets.py"
    try:
        import clip  # noqa: F401
        import torch  # noqa: F401
        import torchvision  # noqa: F401
    except ImportError as exc:
        return False, f"Dependencia UniversalFakeDetect ausente: {exc.name}"
    return True, ""

