"""Runtime probes and model path resolution for IML-ViT."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Optional, Tuple

IML_VIT_CHECKPOINT = "iml-vit_checkpoint.pth"
IML_VIT_DRIVE_FILE_ID = "1xXJGJPW1i5j9Pc1JKd7fJmIAQkvt9jY7"


def _workspace_root() -> Path:
    return Path(__file__).resolve().parents[5]


def iml_vit_repo_dir() -> Path:
    env = os.environ.get("IML_VIT_REPO_DIR")
    if env:
        return Path(env).resolve()
    return (_workspace_root() / "vendor" / "IML-ViT-main").resolve()


def iml_vit_models_target_dir() -> Path:
    env_path = os.environ.get("IML_VIT_MODELS_DIR")
    if env_path:
        return Path(env_path).resolve()
    from app.config import get_settings

    return (Path(get_settings().MODELS_DIR) / "iml_vit").resolve()


def _candidate_checkpoint_dirs() -> list[Path]:
    candidates: list[Path] = [iml_vit_models_target_dir()]
    repo = iml_vit_repo_dir()
    if repo.is_dir():
        candidates.append(repo / "checkpoints")
    return candidates


def resolve_iml_vit_checkpoint() -> Optional[Path]:
    for directory in _candidate_checkpoint_dirs():
        path = directory / IML_VIT_CHECKPOINT
        if path.is_file() and path.stat().st_size > 1_000_000:
            return path.resolve()
    return None


def iml_vit_inference_device():
    import torch

    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def iml_vit_uses_cpu() -> bool:
    return iml_vit_inference_device().type == "cpu"


@lru_cache(maxsize=1)
def iml_vit_runtime_status() -> Tuple[bool, str]:
    repo = iml_vit_repo_dir()
    if not repo.is_dir():
        return (
            False,
            "Codigo IML-ViT ausente. Esperado em vendor/IML-ViT-main.",
        )

    try:
        import torch  # noqa: F401
    except ImportError:
        return False, "PyTorch nao instalado."

    try:
        import albumentations  # noqa: F401
    except ImportError:
        return False, "Dependencia 'albumentations' ausente. Execute: pip install albumentations"

    try:
        import timm  # noqa: F401
    except ImportError:
        return False, "Dependencia 'timm' ausente. Execute: pip install timm fvcore"

    try:
        import fvcore  # noqa: F401
    except ImportError:
        return False, "Dependencia 'fvcore' ausente. Execute: pip install fvcore"

    checkpoint = resolve_iml_vit_checkpoint()
    if checkpoint is None:
        return (
            False,
            "Pesos IML-ViT ausentes. Execute: python scripts/download_iml_vit_weights.py "
            f"(arquivo {IML_VIT_CHECKPOINT} em models/iml_vit/).",
        )

    return True, ""


def clear_runtime_cache() -> None:
    iml_vit_runtime_status.cache_clear()
