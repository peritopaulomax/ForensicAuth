"""Runtime paths and availability for SAFE synthetic image detection (KDD'25)."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

CHECKPOINT_FILENAME = "checkpoint-best.pth"
SAFE_REPO = "Ouxiang-Li/SAFE"
CHECKPOINT_URL = (
    "https://github.com/Ouxiang-Li/SAFE/raw/main/checkpoint/checkpoint-best.pth"
)


def _workspace_root() -> Path:
    return Path(__file__).resolve().parents[5]


def safe_vendor_dir() -> Path:
    return _workspace_root() / "vendor" / "SAFE"


def safe_models_dir() -> Path:
    env = os.environ.get("SAFE_MODELS_DIR")
    if env:
        return Path(env).resolve()
    from app.config import get_settings

    return (Path(get_settings().MODELS_DIR) / "safe").resolve()


def resolve_checkpoint() -> Path | None:
    path = safe_models_dir() / CHECKPOINT_FILENAME
    if path.is_file() and path.stat().st_size > 100_000:
        return path
    vendor_ckpt = safe_vendor_dir() / "checkpoint" / CHECKPOINT_FILENAME
    if vendor_ckpt.is_file() and vendor_ckpt.stat().st_size > 100_000:
        return vendor_ckpt
    return None


def _package_ok() -> tuple[bool, str]:
    missing: list[str] = []
    for module in ("torch", "torchvision", "kornia", "pytorch_wavelets"):
        try:
            __import__(module)
        except ImportError:
            missing.append(module)
    if missing:
        return (
            False,
            "Dependencias SAFE ausentes: "
            + ", ".join(missing)
            + ". Instale: pip install kornia pytorch_wavelets pywavelets",
        )
    if not safe_vendor_dir().is_dir():
        return False, f"Codigo SAFE ausente em {safe_vendor_dir()}"
    return True, ""


def safe_runtime_status() -> tuple[bool, str]:
    ok_pkg, reason = _package_ok()
    if not ok_pkg:
        return False, reason
    ckpt = resolve_checkpoint()
    if ckpt is None:
        return (
            False,
            f"Peso SAFE ausente ({CHECKPOINT_FILENAME}). "
            "Execute: python scripts/download_safe_weights.py",
        )
    return True, ""


@lru_cache(maxsize=1)
def any_safe_ready() -> tuple[bool, str]:
    return safe_runtime_status()
