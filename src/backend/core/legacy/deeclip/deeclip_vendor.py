"""Import isolation for the vendored DeeCLIP repository."""

from __future__ import annotations

import importlib.util
import sys
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from typing import Iterator

from core.legacy.deeclip.deeclip_runtime import deeclip_vendor_dir

_VENDOR_MODULE_PREFIX = "forensicauth_vendor_deeclip"


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Nao foi possivel carregar modulo DeeCLIP em {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@contextmanager
def deeclip_vendor_context() -> Iterator[None]:
    """Temporarily expose DeeCLIP vendor modules under their original names."""
    vendor = deeclip_vendor_dir()
    losses_path = vendor / "losses.py"
    previous_losses = sys.modules.get("losses")

    if str(vendor) not in sys.path:
        sys.path.insert(0, str(vendor))
        added_path = True
    else:
        added_path = False

    try:
        if losses_path.is_file():
            sys.modules["losses"] = _load_module(f"{_VENDOR_MODULE_PREFIX}.losses", losses_path)
        yield
    finally:
        if previous_losses is None:
            sys.modules.pop("losses", None)
        else:
            sys.modules["losses"] = previous_losses
        if added_path:
            try:
                sys.path.remove(str(vendor))
            except ValueError:
                pass


def load_deeclip_class():
    model_path = deeclip_vendor_dir() / "model.py"
    if not model_path.is_file():
        raise RuntimeError(f"model.py DeeCLIP ausente em {model_path}")
    with deeclip_vendor_context():
        module = _load_module(f"{_VENDOR_MODULE_PREFIX}.model", model_path)
    model_class = getattr(module, "DeeCLIP", None)
    if model_class is None:
        raise RuntimeError("Classe DeeCLIP nao encontrada no vendor")
    return model_class
