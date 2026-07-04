"""Runtime paths and availability for Forensic Self-Descriptions (FSD)."""

from __future__ import annotations

import os
from pathlib import Path

FSD_WEIGHT_FILES = ("config.json", "fre.pt", "gmm.pt", "fsd_transforms.pt")


def _workspace_root() -> Path:
    return Path(__file__).resolve().parents[5]


def _models_dir() -> Path:
    from app.config import get_settings

    return Path(get_settings().MODELS_DIR)


def fsd_vendor_dir() -> Path:
    env = os.environ.get("FSD_VENDOR_DIR")
    if env:
        return Path(env).resolve()
    return _workspace_root() / "vendor" / "fsd"


def fsd_weights_dir() -> Path:
    env = os.environ.get("FSD_WEIGHTS_DIR")
    if env:
        return Path(env).resolve()
    return (_models_dir() / "fsd" / "weights").resolve()


def fsd_runtime_status() -> tuple[bool, str]:
    vendor = fsd_vendor_dir()
    if not (vendor / "fsd" / "detector.py").is_file():
        return False, f"Codigo FSD ausente em {vendor}"
    weights = fsd_weights_dir()
    missing = [name for name in FSD_WEIGHT_FILES if not (weights / name).is_file()]
    if missing:
        return False, "Pesos FSD ausentes: " + ", ".join(missing) + ". Execute: python scripts/download_fsd_assets.py"
    try:
        import scipy  # noqa: F401
        import sklearn  # noqa: F401
        import torch  # noqa: F401
    except ImportError as exc:
        return False, f"Dependencia FSD ausente: {exc.name}"
    return True, ""

