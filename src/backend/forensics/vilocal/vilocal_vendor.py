"""Vendor bootstrap for multimediaFor/ViLocal (train_stage2)."""

from __future__ import annotations

import sys
from contextlib import contextmanager

from forensics.vilocal.vilocal_runtime import vilocal_vendor_dir

_ISOLATE_PREFIXES = (
    "model",
    "uniformer",
    "SRM_3D",
    "base_model",
    "wrappers",
    "dataset",
    "loss",
    "metric",
)


def _snapshot_modules(prefixes: tuple[str, ...]) -> dict[str, object]:
    out: dict[str, object] = {}
    for key in list(sys.modules):
        for prefix in prefixes:
            if key == prefix or key.startswith(f"{prefix}."):
                out[key] = sys.modules[key]
                break
    return out


def _purge_modules(prefixes: tuple[str, ...]) -> None:
    for key in list(sys.modules):
        for prefix in prefixes:
            if key == prefix or key.startswith(f"{prefix}."):
                del sys.modules[key]
                break


@contextmanager
def vilocal_vendor_context():
    vendor = vilocal_vendor_dir()
    if not vendor.is_dir():
        raise FileNotFoundError(vendor)
    saved = _snapshot_modules(_ISOLATE_PREFIXES)
    _purge_modules(_ISOLATE_PREFIXES)
    inserted = str(vendor)
    path_inserted = False
    if inserted not in sys.path:
        sys.path.insert(0, inserted)
        path_inserted = True
    try:
        yield vendor
    finally:
        _purge_modules(_ISOLATE_PREFIXES)
        sys.modules.update(saved)
        if path_inserted and inserted in sys.path:
            sys.path.remove(inserted)
