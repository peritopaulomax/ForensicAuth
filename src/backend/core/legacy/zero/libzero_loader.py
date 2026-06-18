"""Load libzero.so_ via cffi (Farid / ZERO grid detection)."""

from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional, Tuple

import numpy as np

_LIBZERO_CDEF = """
void rgb2luminance(double * input, double * output, int X, int Y, int C);
void compute_grid_votes_per_pixel(double * image, int * votes, int X, int Y);
int detect_global_grids(int * votes, double * lnfa_grids, int X, int Y);
typedef struct {
    int x0, y0, x1, y1;
    int grid;
    double lnfa;
} meaningful_reg;
int detect_forgeries(int * votes, int * forgery_mask, int * forgery_mask_reg,
                     meaningful_reg * forged_regions,
                     int X, int Y, int grid_to_exclude, int grid_max);
"""

_FFI: Any = None
_LIB: Any = None
_LIB_ERROR: Optional[str] = None


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _workspace_root() -> Path:
    return Path(__file__).resolve().parents[5]


def _candidate_lib_paths() -> list[Path]:
    env_path = os.environ.get("LIBZERO_PATH")
    candidates: list[Path] = []
    if env_path:
        candidates.append(Path(env_path))

    native = _backend_root() / "lib" / "native"
    candidates.extend(
        [
            native / "libzero.so_",
            native / "libzero.so",
        ]
    )

    legados = _workspace_root() / "Legados" / "imagens"
    if legados.is_dir():
        for child in legados.iterdir():
            if child.name.startswith("04"):
                candidates.extend([child / "libzero.so_", child / "libzero.so"])
                break

    return candidates


def allocate_meaningful_regions(ffi: Any, count: int) -> tuple[Any, Any]:
    """Allocate buffer for detect_forgeries output (cffi 2.x needs explicit cast)."""
    regions = ffi.new("meaningful_reg[]", count)
    regions_ptr = ffi.cast("meaningful_reg *", regions)
    return regions, regions_ptr


def pointer_from_array(ffi: Any, array: np.ndarray) -> Any:
    """ffi.from_buffer wrapper matching ZERO.ipynb P()."""
    typestr = "double*"
    if array.dtype == np.float32:
        typestr = "float*"
    elif array.dtype == bool:
        typestr = "bool*"
    elif array.dtype == np.int32:
        typestr = "int*"
    return ffi.from_buffer(typestr, array, require_writable=True)


@lru_cache(maxsize=1)
def _load_libzero() -> tuple[Any, Any]:
    """Load libzero once; return (ffi, lib) sharing the same FFI instance."""
    global _LIB_ERROR
    if sys.platform == "win32":
        raise OSError(
            "libzero.so_ requer ambiente Linux (servidor ou WSL). "
            "Backend Windows nativo nao suporta ZERO."
        )

    import cffi

    ffi = cffi.FFI()
    ffi.cdef(_LIBZERO_CDEF)

    last_err: Optional[Exception] = None
    for path in _candidate_lib_paths():
        if not path.is_file():
            continue
        try:
            lib = ffi.dlopen(str(path.resolve()))
            return ffi, lib
        except OSError as exc:
            last_err = exc

    msg = "libzero.so_ nao encontrado. Coloque em src/backend/lib/native/ ou defina LIBZERO_PATH."
    if last_err:
        msg = f"{msg} Ultimo erro: {last_err}"
    raise OSError(msg)


def get_libzero() -> Any:
    """Return loaded libzero library or raise OSError."""
    return _load_libzero()[1]


def get_ffi() -> Any:
    """Return the FFI instance bound to the loaded libzero library."""
    return _load_libzero()[0]


def zero_runtime_status() -> Tuple[bool, str]:
    """
    Probe whether ZERO can run on this server.

    Returns (available, reason). reason empty when available.
    """
    if sys.platform == "win32":
        return (
            False,
            "ZERO (libzero) disponivel apenas com backend Linux. Este servidor esta em Windows.",
        )
    try:
        _load_libzero()
        return True, ""
    except OSError as exc:
        return False, str(exc)
