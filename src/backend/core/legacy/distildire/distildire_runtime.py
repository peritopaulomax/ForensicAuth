"""Runtime paths and availability for DistilDIRE (ICML 2024)."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

TECHNIQUE_NAME = "distildire"
MODEL_LABEL = "DistilDIRE (ICML 2024)"

ADM_FILE = "256x256-adm.pt"
CHECKPOINT_FILES = {
    "imagenet": "imagenet-distil-dire-11e.pth",
    "celebahq": "celebahq-distil-dire-34e.pth",
}

CHECKPOINT_URLS = {
    "imagenet": "https://huggingface.co/yevvonlim/distildire/resolve/main/imagenet-distil-dire-11e.pth",
    "celebahq": "https://huggingface.co/yevvonlim/distildire/resolve/main/celebahq-distil-dire-34e.pth",
}
ADM_URL = (
    "https://openaipublic.blob.core.windows.net/diffusion/jul-2021/256x256_diffusion_uncond.pt"
)

CheckpointKind = Literal["imagenet", "celebahq"]


def _workspace_root() -> Path:
    return Path(__file__).resolve().parents[5]


def distildire_vendor_dir() -> Path:
    env = os.environ.get("DISTILDIRE_VENDOR_DIR")
    if env:
        return Path(env).resolve()
    return (_workspace_root() / "vendor" / "distildire").resolve()


def distildire_models_dir() -> Path:
    env = os.environ.get("DISTILDIRE_MODELS_DIR")
    if env:
        return Path(env).resolve()
    from app.config import get_settings

    return (Path(get_settings().MODELS_DIR) / "distildire").resolve()


def distildire_weights_dir() -> Path:
    return distildire_models_dir() / "weights"


def adm_model_path() -> Path:
    override = os.environ.get("DISTILDIRE_ADM_PATH")
    if override:
        return Path(override).resolve()
    return distildire_weights_dir() / ADM_FILE


def checkpoint_path(kind: CheckpointKind = "imagenet") -> Path:
    env = os.environ.get("DISTILDIRE_WEIGHTS_PATH")
    if env:
        return Path(env).resolve()
    return distildire_weights_dir() / CHECKPOINT_FILES[kind]


@lru_cache(maxsize=1)
def distildire_runtime_status(*, require_checkpoint: CheckpointKind = "imagenet") -> tuple[bool, str]:
    vendor = distildire_vendor_dir()
    if not vendor.is_dir():
        return (
            False,
            "Codigo DistilDIRE ausente. Esperado em vendor/distildire "
            "(https://github.com/miraflow/DistilDIRE).",
        )

    required_files = (
        vendor / "networks" / "distill_model.py",
        vendor / "guided_diffusion" / "compute_dire_eps.py",
        vendor / "custommodel.py",
    )
    missing = [p.name for p in required_files if not p.is_file()]
    if missing:
        return False, f"Vendor DistilDIRE incompleto: faltam {', '.join(missing)}."

    try:
        import torch  # noqa: F401
    except ImportError:
        return False, "PyTorch nao instalado."

    weights = distildire_weights_dir()
    ckpt = checkpoint_path(require_checkpoint)
    adm = adm_model_path()
    if not adm.is_file() or adm.stat().st_size < 50_000_000:
        return (
            False,
            f"Modelo ADM ausente em {adm}. Execute: python scripts/download_distildire_weights.py",
        )
    if not ckpt.is_file() or ckpt.stat().st_size < 1_000_000:
        return (
            False,
            f"Checkpoint DistilDIRE ausente em {ckpt}. Execute: python scripts/download_distildire_weights.py",
        )

    return True, ""
