"""In-process std::sort via bundled shared library (Peritus-compatible)."""

from __future__ import annotations

import ctypes
from pathlib import Path

import numpy as np

_LIB: ctypes.CDLL | None = None
_LIB_LOADED = False


def _load_sort_lib() -> ctypes.CDLL | None:
    global _LIB, _LIB_LOADED
    if _LIB_LOADED:
        return _LIB
    _LIB_LOADED = True
    lib_path = Path(__file__).resolve().parents[5] / "tools" / "copy_move_pca_sort.so"
    if not lib_path.is_file():
        return None
    lib = ctypes.CDLL(str(lib_path))
    lib.copy_move_pca_sort_indices.argtypes = [
        ctypes.POINTER(ctypes.c_double),
        ctypes.c_int,
        ctypes.POINTER(ctypes.c_int),
    ]
    lib.copy_move_pca_sort_indices.restype = None
    _LIB = lib
    return lib


def std_sort_indices(keys: np.ndarray) -> np.ndarray:
    """Sort block indices by lexicographic keys using libstdc++ std::sort."""
    nb = keys.shape[0]
    keys_c = np.ascontiguousarray(keys, dtype=np.float64)
    out = np.empty(nb, dtype=np.int32)
    lib = _load_sort_lib()
    if lib is not None:
        lib.copy_move_pca_sort_indices(
            keys_c.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            nb,
            out.ctypes.data_as(ctypes.POINTER(ctypes.c_int)),
        )
        return out
    return np.argsort(keys, kind="heapsort").astype(np.int32)
