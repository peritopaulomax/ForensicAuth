"""Bootstrap DistilDIRE vendor imports."""

from __future__ import annotations

import contextlib
import sys
from pathlib import Path

from core.legacy.distildire.distildire_runtime import distildire_vendor_dir

_NETWORKS_PREFIX = "networks"
_GUIDED_DIFFUSION_PREFIX = "guided_diffusion"


def _snapshot_modules(prefix: str) -> dict[str, object]:
    return {
        k: sys.modules[k]
        for k in list(sys.modules)
        if k == prefix or k.startswith(f"{prefix}.")
    }


def _purge_modules(prefix: str) -> None:
    for key in [k for k in sys.modules if k == prefix or k.startswith(f"{prefix}.")]:
        del sys.modules[key]


@contextlib.contextmanager
def distildire_vendor_context():
    """Isolate DistilDIRE vendor imports from other techniques using `networks`."""
    vendor = distildire_vendor_dir()
    if not vendor.is_dir():
        raise FileNotFoundError(vendor)
    root = str(vendor)
    saved_networks = _snapshot_modules(_NETWORKS_PREFIX)
    saved_guided = _snapshot_modules(_GUIDED_DIFFUSION_PREFIX)
    _purge_modules(_NETWORKS_PREFIX)
    _purge_modules(_GUIDED_DIFFUSION_PREFIX)
    inserted = False
    if root not in sys.path:
        sys.path.insert(0, root)
        inserted = True
    try:
        yield vendor
    finally:
        _purge_modules(_NETWORKS_PREFIX)
        _purge_modules(_GUIDED_DIFFUSION_PREFIX)
        sys.modules.update(saved_networks)
        sys.modules.update(saved_guided)
        if inserted:
            try:
                sys.path.remove(root)
            except ValueError:
                pass
