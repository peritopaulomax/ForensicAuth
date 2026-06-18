"""Runtime paths and availability for VideoFACT (WACV 2024)."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

MODEL_LABEL_XFER = "VideoFACT (Edicoes/Xfer)"
MODEL_LABEL_DF = "VideoFACT (Deepfake)"
TECHNIQUE_NAME = "videofact"

WEIGHT_FILES = {
    "xfer": "videofact_xfer.ckpt",
    "df": "videofact_df.ckpt",
}

XFER_THRESHOLD = 0.40
DF_THRESHOLD = 0.33

DROPBOX_URLS = {
    "xfer": (
        "https://www.dropbox.com/scl/fi/exkdmmp2krsbkc5fblld7/videofact_xfer.ckpt"
        "?rlkey=g52xhouc3h2yqrb5l2gfloiq7&dl=1"
    ),
    "df": (
        "https://www.dropbox.com/scl/fi/euwth7njdi3nj3wi7o8zu/videofact_df.ckpt"
        "?rlkey=hwruc4bui47giukx5urlf1p5j&dl=1"
    ),
}


def _workspace_root() -> Path:
    return Path(__file__).resolve().parents[5]


def videofact_vendor_dir() -> Path:
    return _workspace_root() / "vendor" / "videofact-wacv-2024"


def videofact_models_dir() -> Path:
    env = os.environ.get("VIDEOFACT_MODELS_DIR")
    if env:
        return Path(env).resolve()
    from app.config import get_settings

    return (Path(get_settings().MODELS_DIR) / "videofact").resolve()


def videofact_weights_dir() -> Path:
    return videofact_models_dir() / "weights"


def videofact_config_path() -> Path:
    vendor_cfg = videofact_vendor_dir() / "configs" / "default.yaml"
    if vendor_cfg.is_file():
        return vendor_cfg
    return videofact_models_dir() / "default.yaml"


def weight_path(kind: str) -> Path:
    return videofact_weights_dir() / WEIGHT_FILES[kind]


def _weight_ready(kind: str) -> bool:
    path = weight_path(kind)
    return path.is_file() and path.stat().st_size > 1_000_000


def _package_ok() -> tuple[bool, str]:
    missing: list[str] = []
    for module in ("torch", "torchvision", "cv2", "yaml", "decord", "lightning"):
        try:
            __import__(module)
        except ImportError:
            missing.append(module)
    if missing:
        return False, f"Dependencias ausentes para VideoFACT: {', '.join(missing)}"
    return True, ""


def videofact_runtime_status(*, require_modes: tuple[str, ...] = ("xfer", "df")) -> tuple[bool, str]:
    vendor = videofact_vendor_dir()
    if not vendor.is_dir():
        return False, f"Vendor VideoFACT ausente em {vendor}"

    ok_pkg, pkg_reason = _package_ok()
    if not ok_pkg:
        return False, pkg_reason

    wrapper = vendor / "model" / "videofact_pl_wrapper.py"
    if not wrapper.is_file():
        return False, f"Codigo VideoFACT incompleto em {vendor}"

    missing_weights = [kind for kind in require_modes if not _weight_ready(kind)]
    if missing_weights:
        names = ", ".join(WEIGHT_FILES[k] for k in missing_weights)
        return (
            False,
            f"Pesos VideoFACT ausentes ({names}). Execute: "
            "python scripts/download_videofact_weights.py",
        )

    return True, ""


@lru_cache(maxsize=1)
def default_thresholds() -> dict[str, float]:
    return {"xfer": XFER_THRESHOLD, "df": DF_THRESHOLD}
