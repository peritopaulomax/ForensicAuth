"""Runtime probes and weight path resolution for Noiseprint (PyTorch)."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Optional, Tuple

NOISEPRINT_WEIGHTS_SUBDIR = "pretrained_weights"
REQUIRED_WEIGHT = "model_qf101.pth"
EXPECTED_QFS = list(range(51, 102))


def _workspace_root() -> Path:
    return Path(__file__).resolve().parents[5]


def noiseprint_repo_dir() -> Path:
    env = os.environ.get("NOISEPRINT_REPO_DIR")
    if env:
        return Path(env).resolve()
    return (_workspace_root() / "vendor" / "noiseprint-pytorch-main").resolve()


def noiseprint_models_target_dir() -> Path:
    env_path = os.environ.get("NOISEPRINT_MODELS_DIR")
    if env_path:
        return Path(env_path).resolve()
    from app.config import get_settings

    return (Path(get_settings().MODELS_DIR) / "noiseprint").resolve()


def _candidate_weights_dirs() -> list[Path]:
    candidates: list[Path] = [noiseprint_models_target_dir() / NOISEPRINT_WEIGHTS_SUBDIR]
    repo = noiseprint_repo_dir()
    if repo.is_dir():
        candidates.append(repo / NOISEPRINT_WEIGHTS_SUBDIR)
    return candidates


def list_missing_noiseprint_weights(directory: Path) -> list[int]:
    missing: list[int] = []
    for qf in EXPECTED_QFS:
        if not (directory / f"model_qf{qf}.pth").is_file():
            missing.append(qf)
    return missing


def resolve_noiseprint_weights_dir() -> Optional[Path]:
    for directory in _candidate_weights_dirs():
        if directory.is_dir() and (directory / REQUIRED_WEIGHT).is_file():
            return directory.resolve()
    return None


def noiseprint_inference_device():
    from core.gpu_inference import resolve_inference_device

    return resolve_inference_device()


def noiseprint_uses_cpu() -> bool:
    return noiseprint_inference_device().type == "cpu"


@lru_cache(maxsize=1)
def noiseprint_runtime_status() -> Tuple[bool, str]:
    repo = noiseprint_repo_dir()
    if not repo.is_dir():
        return (
            False,
            "Codigo Noiseprint ausente. Esperado em vendor/noiseprint-pytorch-main.",
        )

    try:
        import torch  # noqa: F401
    except ImportError:
        return False, "PyTorch nao instalado."

    weights = resolve_noiseprint_weights_dir()
    if weights is None:
        return (
            False,
            "Pesos Noiseprint ausentes. Execute: python scripts/download_noiseprint_weights.py "
            f"(pelo menos {REQUIRED_WEIGHT} em models/noiseprint/pretrained_weights/).",
        )

    missing = list_missing_noiseprint_weights(weights)
    if missing:
        preview = ", ".join(str(qf) for qf in missing[:8])
        suffix = "..." if len(missing) > 8 else ""
        return (
            False,
            "Pesos Noiseprint incompletos "
            f"({len(missing)}/{len(EXPECTED_QFS)} ausentes, ex.: QF {preview}{suffix}). "
            "Execute: python scripts/download_noiseprint_weights.py",
        )

    return True, ""


def clear_runtime_cache() -> None:
    noiseprint_runtime_status.cache_clear()
