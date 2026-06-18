"""Vendor bootstrap for lukasHoel/fake-video-detection."""

from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path

from core.legacy.lowres_fake_video.lfv_runtime import lfv_vendor_dir

_NETWORKS_PREFIX = "networks"


def _snapshot_networks_modules() -> dict[str, object]:
    return {k: sys.modules[k] for k in list(sys.modules) if k == _NETWORKS_PREFIX or k.startswith(f"{_NETWORKS_PREFIX}.")}


def _purge_networks_modules() -> None:
    for key in [k for k in sys.modules if k == _NETWORKS_PREFIX or k.startswith(f"{_NETWORKS_PREFIX}.")]:
        del sys.modules[key]


@contextmanager
def lfv_vendor_context():
    vendor = lfv_vendor_dir()
    if not vendor.is_dir():
        raise FileNotFoundError(vendor)
    saved_networks = _snapshot_networks_modules()
    _purge_networks_modules()
    inserted = str(vendor)
    path_inserted = False
    if inserted not in sys.path:
        sys.path.insert(0, inserted)
        path_inserted = True
    try:
        yield vendor
    finally:
        _purge_networks_modules()
        sys.modules.update(saved_networks)
        if path_inserted and inserted in sys.path:
            sys.path.remove(inserted)
