"""Runtime paths and availability for STIL deepfake video detection."""

from __future__ import annotations

import os
from pathlib import Path

MODEL_LABEL = "STIL (Spatiotemporal Inconsistency)"
TECHNIQUE_NAME = "stil_video_detection"
CLIP_SIZE = 8
THRESHOLD = 0.5

SCNET_URL = "https://backseason.oss-cn-beijing.aliyuncs.com/scnet/scnet50_v1d-4109d1e1.pth"
SCNET_FILE = "scnet50_v1d.pth"
TRAINED_FILE = "stil_trained.pth"


def _workspace_root() -> Path:
    return Path(__file__).resolve().parents[5]


def stil_vendor_dir() -> Path:
    return _workspace_root() / "vendor" / "deepfakebench"


def stil_models_dir() -> Path:
    env = os.environ.get("STIL_MODELS_DIR")
    if env:
        return Path(env).resolve()
    from app.config import get_settings

    return (Path(get_settings().MODELS_DIR) / "stil").resolve()


def stil_weights_dir() -> Path:
    return stil_models_dir() / "weights"


def trained_weight_path() -> Path:
    custom = os.environ.get("STIL_WEIGHTS_PATH")
    if custom:
        return Path(custom).resolve()
    return stil_weights_dir() / TRAINED_FILE


def scnet_weight_path() -> Path:
    return stil_weights_dir() / SCNET_FILE


def _package_ok() -> tuple[bool, str]:
    missing: list[str] = []
    for module in ("torch", "torchvision", "cv2", "decord", "numpy"):
        try:
            __import__(module)
        except ImportError:
            missing.append(module)
    return (False, f"Dependencias ausentes para STIL: {', '.join(missing)}") if missing else (True, "")


def stil_runtime_status() -> tuple[bool, str]:
    vendor = stil_vendor_dir()
    if not vendor.is_dir():
        return False, f"Vendor DeepfakeBench ausente em {vendor}"

    model_file = Path(__file__).parent / "stil_model.py"
    if not model_file.is_file():
        return False, "Modulo STIL ausente (stil_model.py)"

    ok_pkg, pkg_reason = _package_ok()
    if not ok_pkg:
        return False, pkg_reason

    w = trained_weight_path()
    if w.is_file() and w.stat().st_size > 100_000:
        return True, ""

    scnet = scnet_weight_path()
    scnet_ok = scnet.is_file() and scnet.stat().st_size > 1_000_000
    return (
        False,
        "Checkpoint STIL treinado ausente. Os repositorios GitHub (wizyoung/STIL, Tencent/TFace, "
        "DeepfakeBench) publicam apenas codigo e backbone ImageNet (SCNet) — nao ha stil_best.pth "
        "no release v1.0.1 do DeepfakeBench (somente detectores de imagem). "
        f"Coloque um .pth/.tar treinado em {w} ou defina STIL_WEIGHTS_PATH. "
        + (f"Backbone SCNet ja baixado em {scnet}." if scnet_ok else "Execute: python scripts/download_stil_weights.py"),
    )
