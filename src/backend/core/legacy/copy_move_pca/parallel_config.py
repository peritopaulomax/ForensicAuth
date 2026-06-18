"""Thread-pool configuration for Copy-Move PCA (Numba, OpenCV, BLAS)."""

from __future__ import annotations

import os
import sys
from functools import lru_cache


def resolve_copy_move_n_jobs(explicit: int | None = None) -> int:
    """Resolve worker count: explicit arg > env > settings > cpu_count."""
    if explicit is not None and explicit > 0:
        return explicit

    env_val = os.environ.get("COPY_MOVE_PCA_N_JOBS", "").strip()
    if env_val.isdigit() and int(env_val) > 0:
        return int(env_val)

    try:
        from app.config import get_settings

        configured = get_settings().COPY_MOVE_PCA_N_JOBS
        if configured > 0:
            return configured
    except Exception:
        pass

    return max(1, os.cpu_count() or 1)


@lru_cache(maxsize=1)
def configure_copy_move_parallelism(n_jobs: int | None = None) -> int:
    """
    Apply one thread budget to Numba, OpenCV and BLAS/OpenMP backends.

    Phases (PCA → vote → mark) run sequentially, so peak CPU usage stays near *n*
    when all pools share the same limit.
    """
    n = resolve_copy_move_n_jobs(n_jobs)

    os.environ["OPENBLAS_NUM_THREADS"] = str(n)
    os.environ["OMP_NUM_THREADS"] = str(n)
    os.environ["MKL_NUM_THREADS"] = str(n)
    os.environ["OPENBLAS_MAIN_FREE"] = "1"

    # Numba reads NUMBA_NUM_THREADS at import; changing it later triggers reload errors.
    if "numba" not in sys.modules:
        os.environ["NUMBA_NUM_THREADS"] = str(n)

    import cv2

    cv2.setNumThreads(n)

    numba_n = n
    if "numba" in sys.modules:
        try:
            import numba

            if numba.get_num_threads() != n:
                numba.set_num_threads(n)
        except (RuntimeError, ValueError):
            try:
                import numba

                numba_n = numba.get_num_threads()
            except Exception:
                numba_n = n

    return numba_n
