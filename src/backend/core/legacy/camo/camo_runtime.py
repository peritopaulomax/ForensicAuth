"""Runtime paths and availability for CAMO (BitMind UCF MoE)."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

HF_REPO = "bitmind/bm-ucf"
WEIGHT_FILES = (
    "bm-general-v1.pth",
    "bm-faces-v1.pth",
    "xception-best.pth",
)
CONFIG_FILES = (
    "bm-general-config-v1.yaml",
    "bm-faces-config-v1.yaml",
)
DLIB_PREDICTOR = "shape_predictor_81_face_landmarks.dat"
MODEL_LABEL = "CAMO (BitMind UCF MoE)"


def _workspace_root() -> Path:
    return Path(__file__).resolve().parents[5]


def camo_vendor_dir() -> Path:
    return _workspace_root() / "vendor" / "bitmind-subnet"


def camo_models_dir() -> Path:
    env = os.environ.get("CAMO_MODELS_DIR")
    if env:
        return Path(env).resolve()
    from app.config import get_settings

    return (Path(get_settings().MODELS_DIR) / "camo").resolve()


def camo_weights_dir() -> Path:
    return camo_models_dir() / "weights"


def camo_configs_dir() -> Path:
    return camo_models_dir() / "configs"


def resolve_dlib_predictor() -> Path | None:
    for candidate in (
        camo_models_dir() / DLIB_PREDICTOR,
        camo_vendor_dir()
        / "bitmind"
        / "dataset_processing"
        / "dlib_tools"
        / DLIB_PREDICTOR,
    ):
        if candidate.is_file() and candidate.stat().st_size > 1_000_000:
            return candidate
    return None


def _weight_ready(name: str) -> bool:
    path = camo_weights_dir() / name
    return path.is_file() and path.stat().st_size > 100_000


def _config_ready(name: str) -> bool:
    path = camo_configs_dir() / name
    return path.is_file() and path.stat().st_size > 100


def _package_ok() -> tuple[bool, str]:
    missing: list[str] = []
    for module in ("torch", "torchvision", "dlib", "cv2", "skimage", "huggingface_hub", "yaml"):
        try:
            __import__(module)
        except ImportError:
            missing.append(module)
    if missing:
        return (
            False,
            "Dependencias CAMO ausentes: "
            + ", ".join(missing)
            + ". Instale dlib, scikit-image, huggingface_hub (requirements-gpu.txt).",
        )
    if not camo_vendor_dir().is_dir():
        return False, f"Codigo BitMind ausente em {camo_vendor_dir()}"
    return True, ""


def camo_runtime_status() -> tuple[bool, str]:
    ok_pkg, reason = _package_ok()
    if not ok_pkg:
        return False, reason

    predictor = resolve_dlib_predictor()
    if predictor is None:
        return (
            False,
            f"Predictor dlib ausente ({DLIB_PREDICTOR}). "
            "Execute: python scripts/download_camo_weights.py",
        )

    missing_weights = [name for name in WEIGHT_FILES if not _weight_ready(name)]
    if missing_weights:
        return (
            False,
            f"Pesos CAMO ausentes ({', '.join(missing_weights)}). "
            "Execute: python scripts/download_camo_weights.py",
        )

    missing_configs = [name for name in CONFIG_FILES if not _config_ready(name)]
    if missing_configs:
        return (
            False,
            f"Configs CAMO ausentes ({', '.join(missing_configs)}). "
            "Execute: python scripts/download_camo_weights.py",
        )
    return True, ""


@lru_cache(maxsize=1)
def any_camo_ready() -> tuple[bool, str]:
    return camo_runtime_status()
