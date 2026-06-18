"""Isolated imports from vendor/IML-ViT-main (avoids backend utils/ shadowing)."""

from __future__ import annotations

import importlib.util
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from core.legacy.iml_vit.iml_vit_runtime import iml_vit_repo_dir

_VENDOR_PKG = "iml_vit_vendor"


def _load_vendor_file(module_name: str, file_path: Path) -> Any:
    full_name = f"{_VENDOR_PKG}.{module_name}"
    if full_name in sys.modules:
        return sys.modules[full_name]

    spec = importlib.util.spec_from_file_location(full_name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Nao foi possivel carregar modulo vendor: {file_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[full_name] = module
    spec.loader.exec_module(module)
    return module


def load_edge_generator_class():
    repo = iml_vit_repo_dir()
    module = _load_vendor_file("edge_generator", repo / "utils" / "edge_generator.py")
    return module.EdgeGenerator


def load_get_albu_transforms():
    repo = iml_vit_repo_dir()
    module = _load_vendor_file("iml_transforms", repo / "utils" / "iml_transforms.py")
    return module.get_albu_transforms


def load_iml_vit_model_class():
    repo = iml_vit_repo_dir()
    with vendor_repo_on_path():
        module = _load_vendor_file("iml_vit_model", repo / "iml_vit_model.py")
    return module.iml_vit_model


@contextmanager
def vendor_repo_on_path() -> Iterator[None]:
    """Temporarily prioritize vendor repo and unblock `modules`/`iml_vit_model` imports."""
    root = str(iml_vit_repo_dir())
    inserted = False
    if root not in sys.path:
        sys.path.insert(0, root)
        inserted = True

    saved_utils = sys.modules.get("utils")
    backend_utils = _is_backend_utils(saved_utils)
    if backend_utils:
        for key in list(sys.modules):
            if key == "utils" or key.startswith("utils."):
                mod = sys.modules.get(key)
                if mod is not None and _is_backend_utils(mod):
                    del sys.modules[key]

    try:
        yield
    finally:
        if backend_utils and saved_utils is not None:
            sys.modules["utils"] = saved_utils
        if inserted and sys.path and sys.path[0] == root:
            sys.path.pop(0)


def _is_backend_utils(module: Any) -> bool:
    file_path = str(getattr(module, "__file__", "") or "")
    return "/src/backend/utils" in file_path.replace("\\", "/")
