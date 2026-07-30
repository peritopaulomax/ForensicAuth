"""Vendor bootstrap for multimediaFor/TruVIL."""

from __future__ import annotations

import sys
from contextlib import contextmanager

from forensics.truvil.truvil_runtime import truvil_vendor_dir

# Flat imports in vendor (model, uniformer, HP3D, …).
_ISOLATE_PREFIXES = (
    "model",
    "uniformer",
    "AttentionModule",
    "HP3D",
    "segformer_head",
    "base_model",
    "wrappers",
    "base_dataset",
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
def truvil_vendor_context():
    vendor = truvil_vendor_dir()
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
