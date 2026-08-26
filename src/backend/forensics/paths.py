"""Roots estaveis para motores forenses (independente da profundidade do modulo)."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def workspace_root() -> Path:
    """Raiz do workspace (codigo + vendor + models).

    Em producao usa FORENSICAUTH_WORKSPACE_ROOT (ex.: /opt/forensicauth).
    Em dev, procura AGENTS.md + vendor/ a partir do arquivo atual.
    """
    env = os.environ.get("FORENSICAUTH_WORKSPACE_ROOT")
    if env:
        return Path(env).resolve()

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
