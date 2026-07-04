"""Import isolation for the vendored CLIDE repository."""

from __future__ import annotations

import importlib.util
import sys
from functools import lru_cache
from pathlib import Path
from types import ModuleType

from core.legacy.clide.clide_runtime import clide_vendor_dir


@lru_cache(maxsize=1)
def load_detection_module() -> ModuleType:
    path = clide_vendor_dir() / "detection.py"
    if not path.is_file():
        raise RuntimeError(f"detection.py CLIDE ausente em {path}")
    spec = importlib.util.spec_from_file_location("forensicauth_vendor_clide_detection", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Nao foi possivel carregar CLIDE em {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
