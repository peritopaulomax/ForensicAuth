"""Roots estaveis para motores forenses (independente da profundidade do modulo)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def workspace_root() -> Path:
    """Raiz do repositorio (AGENTS.md + vendor/)."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "AGENTS.md").is_file() and (parent / "vendor").is_dir():
            return parent
    # forensics/paths.py -> backend -> src -> repo
    return here.parents[3]


@lru_cache(maxsize=1)
def backend_root() -> Path:
    """``src/backend``."""
    return Path(__file__).resolve().parents[1]
