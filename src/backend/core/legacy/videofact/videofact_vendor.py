"""Bootstrap do vendor VideoFACT sem Gradio."""

from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path

from core.legacy.videofact.videofact_runtime import videofact_vendor_dir

_INSERTED_PATHS: list[str] = []


def _insert_sys_paths(vendor: Path) -> None:
    global _INSERTED_PATHS
    for path in (vendor,):
        text = str(path)
        if text not in sys.path:
            sys.path.insert(0, text)
            _INSERTED_PATHS.append(text)


def bootstrap_videofact_vendor() -> Path:
    vendor = videofact_vendor_dir()
    if not vendor.is_dir():
        raise FileNotFoundError(f"Vendor VideoFACT nao encontrado: {vendor}")
    _insert_sys_paths(vendor)
    return vendor


@contextmanager
def videofact_vendor_context():
    bootstrap_videofact_vendor()
    try:
        yield
    finally:
        pass
