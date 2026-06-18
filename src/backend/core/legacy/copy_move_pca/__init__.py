"""Copy-Move PCA (Popescu & Farid 2004) — Peritus port."""

from __future__ import annotations

import os
import sys

from core.legacy.copy_move_pca.parallel_config import resolve_copy_move_n_jobs

# Apply Numba thread budget before numba is imported (pipeline pulls in numba_kernels).
if "numba" not in sys.modules:
    _n_jobs = resolve_copy_move_n_jobs()
    os.environ.setdefault("NUMBA_NUM_THREADS", str(_n_jobs))

from core.legacy.copy_move_pca.pipeline import (
    CopyMovePcaParams,
    DEFAULT_PARAMS,
    estimate_memory_bytes,
    prepare_gray,
    run_copy_move_pca,
)

__all__ = [
    "CopyMovePcaParams",
    "DEFAULT_PARAMS",
    "estimate_memory_bytes",
    "prepare_gray",
    "run_copy_move_pca",
]
