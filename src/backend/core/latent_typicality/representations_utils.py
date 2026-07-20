"""Helpers for audio representation matrices (sample IDs, embedding I/O)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from core.latent_typicality.features import DETECTORS

ORIGINAL_AUGMENTATION_TAG = "original"
_AUDIO_EXTENSIONS = (".wav", ".flac", ".mp3", ".ogg", ".opus", ".m4a")


def source_id_stem(source_id: str) -> str:
    """Stable id stem: strip only real audio extensions, not dots inside protocol ids."""
    s = str(source_id).strip()
    lower = s.lower()
    for ext in _AUDIO_EXTENSIONS:
        if lower.endswith(ext):
            return s[: -len(ext)]
    return s


def resolve_parent_source_id(row: dict[str, Any] | Any) -> str:
    """Stable parent id for augmented rows (manifest already sets parent_source_id)."""
    if hasattr(row, "get"):
        parent = row.get("parent_source_id")
        source_id = str(row.get("source_id") or "").strip()
        augmentation = str(row.get("augmentation") or "").strip()
    else:
        parent = getattr(row, "parent_source_id", None)
        source_id = str(getattr(row, "source_id", "") or "").strip()
        augmentation = str(getattr(row, "augmentation", "") or "").strip()

    if parent is not None and str(parent).strip():
        return str(parent).strip()

    if augmentation:
        suffix = f"_{augmentation}"
        if source_id.endswith(suffix):
            return source_id[: -len(suffix)]
    return source_id


def build_sample_id(
    *,
    dataset: str,
    generator: str,
    source_id: str,
    augmentation: str = "",
) -> str:
    stem = source_id_stem(source_id)
    aug = (augmentation or "").strip() or ORIGINAL_AUGMENTATION_TAG
    return f"{dataset}__{generator}__{stem}__{aug}"


def parse_sample_id(sample_id: str) -> dict[str, str]:
    parts = str(sample_id).split("__")
    if len(parts) < 4:
        raise ValueError(f"sample_id invalido: {sample_id}")
    return {
        "dataset": parts[0],
        "generator": parts[1],
        "source_stem": parts[2],
        "augmentation": "__".join(parts[3:]),
    }


def load_embeddings_row(row: pd.Series, detectors: tuple[str, ...] = DETECTORS) -> dict[str, np.ndarray]:
    out: dict[str, np.ndarray] = {}
    for detector in detectors:
        path = row.get(f"{detector}_embedding_path")
        if not path or (isinstance(path, float) and np.isnan(path)):
            raise RuntimeError(f"Embedding ausente para detector {detector}")
        out[detector] = np.load(str(path))
    return out


def row_has_embeddings(row: pd.Series, detectors: tuple[str, ...] = DETECTORS) -> bool:
    for detector in detectors:
        path = row.get(f"{detector}_embedding_path")
        if not path or (isinstance(path, float) and np.isnan(path)):
            return False
        if not Path(str(path)).is_file():
            return False
    return True


def representations_matrix_available(path: Path) -> bool:
    return path.is_file() and path.stat().st_size > 0
