"""Runtime paths and availability for official GRIP CLIP-D."""

from __future__ import annotations

import os
from pathlib import Path


def _workspace_root() -> Path:
    return Path(__file__).resolve().parents[5]


def _models_dir() -> Path:
    from app.config import get_settings

    return Path(get_settings().MODELS_DIR)


def clipd_vendor_dir() -> Path:
    env = os.environ.get("GRIP_CLIPD_VENDOR_DIR") or os.environ.get("TRUEBEES_CLIPD_VENDOR_DIR")
    if env:
        return Path(env).resolve()
    return _workspace_root() / "vendor" / "grip_clipbased_synthetic"


def clipd_weights_dir() -> Path:
    env = os.environ.get("GRIP_CLIPD_WEIGHTS_DIR")
    if env:
        return Path(env).resolve()
    local = (_models_dir() / "grip_clipd" / "weights").resolve()
    if local.is_dir():
        return local
    return (clipd_vendor_dir() / "weights").resolve()


def clipd_weights_path(model_name: str = "clipdet_latent10k_plus") -> Path:
    return clipd_weights_dir() / model_name / "weights.pth"


def clipd_config_path(model_name: str = "clipdet_latent10k_plus") -> Path:
    return clipd_weights_dir() / model_name / "config.yaml"


def clipd_runtime_status(model_name: str = "clipdet_latent10k_plus") -> tuple[bool, str]:
    vendor = clipd_vendor_dir()
    if not (vendor / "main.py").is_file() or not (vendor / "networks" / "openclipnet.py").is_file():
        return False, f"Codigo oficial GRIP CLIP-D ausente em {vendor}"
    weights = clipd_weights_path(model_name)
    config = clipd_config_path(model_name)
    if not config.is_file():
        return False, f"Config GRIP CLIP-D ausente em {config}. Execute: python scripts/download_truebees_clipd_assets.py"
    if not weights.is_file() or weights.stat().st_size < 1000:
        return False, f"Pesos GRIP CLIP-D ausentes em {weights}. Execute: python scripts/download_truebees_clipd_assets.py"
    try:
        import open_clip  # noqa: F401
        import torch  # noqa: F401
        import torchvision  # noqa: F401
        import yaml  # noqa: F401
    except ImportError as exc:
        return False, f"Dependencia GRIP CLIP-D ausente: {exc.name}"
    return True, ""

