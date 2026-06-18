"""Carrega modulos do vendor IAPL sem colidir com o pacote backend `models`."""

from __future__ import annotations

import importlib
import sys
from contextlib import contextmanager
from pathlib import Path

from core.legacy.iapl.iapl_runtime import iapl_vendor_dir


def _stash_backend_models() -> tuple[object | None, dict[str, object]]:
    backend_models = sys.modules.get("models")
    backend_subs = {k: v for k, v in sys.modules.items() if k.startswith("models.")}
    sys.modules.pop("models", None)
    for key in backend_subs:
        sys.modules.pop(key, None)
    return backend_models, backend_subs


def _restore_backend_models(
    backend_models: object | None,
    backend_subs: dict[str, object],
) -> None:
    if backend_models is not None:
        sys.modules["models"] = backend_models
    for key, module in backend_subs.items():
        sys.modules[key] = module


def patch_clip_loader(clip_path: Path) -> None:
    import models.clip_models as clip_models  # type: ignore[import-untyped]

    original = clip_models.load_clip_to_cpu
    resolved = str(clip_path)

    def _load(
        _model_path: str,
        n_ctx: int,
        adapter_list_vit: list,
        adapter_list_text: list,
        prompt_depth: int,
        gate: bool,
    ):
        return original(resolved, n_ctx, adapter_list_vit, adapter_list_text, prompt_depth, gate)

    clip_models.load_clip_to_cpu = _load


@contextmanager
def iapl_vendor_context(*, clip_path: Path):
    vendor = str(iapl_vendor_dir().resolve())
    backend_models, backend_subs = _stash_backend_models()
    inserted = vendor not in sys.path
    if inserted:
        sys.path.insert(0, vendor)

    vendor_modules = [
        key
        for key in list(sys.modules)
        if key in {"models", "augmix", "augmix_ops", "utils"}
        or key.startswith(("models.", "utils."))
    ]
    for key in vendor_modules:
        sys.modules.pop(key, None)

    try:
        importlib.invalidate_caches()
        patch_clip_loader(clip_path)
        yield
    finally:
        for key in vendor_modules:
            sys.modules.pop(key, None)
        for key in list(sys.modules):
            if key in {"models", "augmix", "augmix_ops", "utils"} or key.startswith(
                ("models.", "utils.")
            ):
                sys.modules.pop(key, None)
        if inserted:
            sys.path.remove(vendor)
        _restore_backend_models(backend_models, backend_subs)
