"""Runtime probes and model path resolution for SAFIRE."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Optional, Tuple

SAFIRE_CHECKPOINT = "safire.pth"
SAM_CHECKPOINT = "sam_vit_b_01ec64.pth"
SAM_URL = "https://dl.fbaipublicfiles.com/segment_anything/sam_vit_b_01ec64.pth"
# Official SAFIRE weights are distributed via the paper's Google Drive folder.
SAFIRE_DRIVE_FOLDER = "1NRxep2G42OnVwCR9sGdf1iPqhCUrGmv2"


def _workspace_root() -> Path:
    return Path(__file__).resolve().parents[5]


def safire_repo_dir() -> Path:
    env = os.environ.get("SAFIRE_REPO_DIR")
    if env:
        return Path(env).resolve()
    return (_workspace_root() / "vendor" / "SAFIRE-main").resolve()


def safire_models_target_dir() -> Path:
    env_path = os.environ.get("SAFIRE_MODELS_DIR")
    if env_path:
        return Path(env_path).resolve()
    from app.config import get_settings

    return (Path(get_settings().MODELS_DIR) / "safire").resolve()


def _models_dir() -> Path:
    from app.config import get_settings

    return Path(get_settings().MODELS_DIR)


def _candidate_model_dirs() -> list[Path]:
    candidates: list[Path] = [safire_models_target_dir()]
    repo = safire_repo_dir()
    if repo.is_dir():
        candidates.append(repo)
    return candidates


def resolve_safire_models_dir() -> Optional[Path]:
    """Return directory containing safire.pth and sam_vit_b_01ec64.pth."""
    for directory in _candidate_model_dirs():
        if not directory.is_dir():
            continue
        if (directory / SAFIRE_CHECKPOINT).is_file() and (directory / SAM_CHECKPOINT).is_file():
            return directory.resolve()
    return None


def safire_inference_device():
    """CUDA when available; otherwise CPU (lento, mas funcional)."""
    from core.gpu_inference import resolve_inference_device

    return resolve_inference_device()


def safire_uses_cpu() -> bool:
    return safire_inference_device().type == "cpu"


@lru_cache(maxsize=1)
def safire_runtime_status() -> Tuple[bool, str]:
    repo = safire_repo_dir()
    if not repo.is_dir():
        return (
            False,
            "Codigo SAFIRE ausente. Esperado em vendor/SAFIRE-main (clone do repositorio oficial).",
        )

    try:
        import torch  # noqa: F401
    except ImportError:
        return False, "PyTorch nao instalado. Instale requirements-gpu.txt (ou torch CPU) no ambiente."

    try:
        import monai  # noqa: F401
    except ImportError:
        return False, "Dependencia 'monai' ausente. Execute: pip install monai scikit-learn"

    models = resolve_safire_models_dir()
    if models is None:
        return (
            False,
            "Pesos SAFIRE ausentes. Execute: python scripts/download_safire_weights.py "
            "(safire.pth + sam_vit_b_01ec64.pth em models/safire/).",
        )

    return True, ""


def clear_runtime_cache() -> None:
    safire_runtime_status.cache_clear()
