"""Runtime paths and availability for GRIP-UNINA B-Free."""

from __future__ import annotations

import os
from pathlib import Path


MODEL_NAME = "BFREE_dino2reg4"


def _workspace_root() -> Path:
    return Path(__file__).resolve().parents[5]


def _models_dir() -> Path:
    from app.config import get_settings

    return Path(get_settings().MODELS_DIR)


def bfree_vendor_dir() -> Path:
    env = os.environ.get("BFREE_VENDOR_DIR")
    if env:
        return Path(env).resolve()
    for candidate in (
        _workspace_root() / "vendor" / "bfree" / "code",
        _workspace_root() / "vendor" / "B-Free" / "code",
    ):
        if candidate.exists():
            return candidate.resolve()
    return (_workspace_root() / "vendor" / "bfree" / "code").resolve()


def bfree_weights_dir() -> Path:
    env = os.environ.get("BFREE_WEIGHTS_DIR")
    if env:
        return Path(env).resolve()
    local = (_models_dir() / "bfree" / "weights").resolve()
    if local.is_dir():
        return local
    return (bfree_vendor_dir() / "weights").resolve()


def bfree_config_path(model_name: str = MODEL_NAME) -> Path:
    return bfree_weights_dir() / model_name / "config.yaml"


def bfree_weights_path(model_name: str = MODEL_NAME) -> Path:
    return bfree_weights_dir() / model_name / "model_epoch_best.pth"


def bfree_runtime_status() -> tuple[bool, str]:
    vendor = bfree_vendor_dir()
    if not (vendor / "networks" / "__init__.py").is_file():
        return False, f"Codigo B-Free ausente em {vendor}. Execute: python scripts/download_bfree_assets.py"
    config = bfree_config_path()
    weights = bfree_weights_path()
    if not config.is_file():
        return False, f"Config B-Free ausente em {config}. Execute: python scripts/download_bfree_assets.py"
    if not weights.is_file() or weights.stat().st_size < 1000:
        return False, f"Pesos B-Free ausentes em {weights}. Execute: python scripts/download_bfree_assets.py"
    try:
        import timm  # noqa: F401
        import torch  # noqa: F401
        import torchvision  # noqa: F401
        import yaml  # noqa: F401
    except ImportError as exc:
        return False, f"Dependencia B-Free ausente: {exc.name}"
    return True, ""
