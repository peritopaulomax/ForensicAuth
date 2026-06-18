"""Co-Transformers official inference (AAAI 2026, IMDLBenCo registry).

Reference: https://github.com/ProgrameThinking/Co-Transformers
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable

import numpy as np
import torch
from PIL import Image

from core.legacy.imdlbenco.imdlbenco_catalog import get_method
from core.legacy.imdlbenco.imdlbenco_preprocess import postprocess_mask, preprocess_single_image
from core.legacy.imdlbenco.imdlbenco_runtime import (
    co_transformers_vendor_root,
    resolve_co_transformers_checkpoint,
    resolve_co_transformers_noiseprint,
    resolve_co_transformers_segformer_pretrain,
)

ProgressFn = Callable[[int, str], None] | None

MODEL_REGISTRY_NAME = "CoTransformers"


@dataclass
class CoTransformersOfficialResult:
    input_image: Image.Image
    heatmap_image: Image.Image
    overlay_image: Image.Image
    mask_image: Image.Image
    original_size: tuple[int, int]
    mean_score: float
    inference_device: str
    gpu_fallback_reason: str | None = None
    gpu_fallback_warning: str | None = None


def _report(on_progress: ProgressFn, pct: int, label: str) -> None:
    if on_progress:
        on_progress(pct, label)


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


def _install_vendor_namespace_package(name: str, package_dir: Path) -> None:
    """Expose vendor subpackage on sys.path without clashing with ForensicAuth ``models``."""
    spec = importlib.util.spec_from_loader(name, loader=None)
    if spec is None:
        raise RuntimeError(f"Falha ao criar spec para pacote vendor {name}")
    spec.submodule_search_locations = [str(package_dir)]
    module = importlib.util.module_from_spec(spec)
    module.__path__ = [str(package_dir)]  # type: ignore[attr-defined]
    sys.modules[name] = module


@lru_cache(maxsize=1)
def _ensure_co_transformers_registered() -> None:
    """Import vendor CoTransformers and register in IMDLBenCo MODELS."""
    from IMDLBenCo.registry import MODELS

    try:
        if MODELS.get(MODEL_REGISTRY_NAME) is not None:
            return
    except KeyError:
        pass

    vendor_root = co_transformers_vendor_root().resolve()
    if not vendor_root.is_dir():
        raise RuntimeError("Codigo Co-Transformers ausente em vendor/Co-Transformers-main.")

    vendor = str(vendor_root)
    if vendor not in sys.path:
        sys.path.insert(0, vendor)

    backend_models, backend_subs = _stash_backend_models()
    try:
        _install_vendor_namespace_package("models", vendor_root / "models")
        _install_vendor_namespace_package("common", vendor_root / "common")
        importlib.import_module("cotransformer")
    finally:
        _restore_backend_models(backend_models, backend_subs)

    try:
        registered = MODELS.get(MODEL_REGISTRY_NAME) is not None
    except KeyError:
        registered = False
    if not registered:
        raise RuntimeError(f"{MODEL_REGISTRY_NAME} nao registrado apos import do vendor.")


def _load_checkpoint_state(ckpt_path: Path) -> dict:
    try:
        obj = torch.load(str(ckpt_path), map_location="cpu", weights_only=False)
    except TypeError:
        obj = torch.load(str(ckpt_path), map_location="cpu")
    if isinstance(obj, dict) and "model" in obj:
        return obj["model"]
    if isinstance(obj, dict):
        return obj
    raise RuntimeError(f"Checkpoint Co-Transformers invalido: {ckpt_path}")


def official_runtime_ready() -> tuple[bool, str]:
    try:
        import IMDLBenCo  # noqa: F401
    except ImportError as exc:
        return False, f"Pacote imdlbenco ausente: {exc}"

    if not co_transformers_vendor_root().is_dir():
        return (
            False,
            "Repositorio Co-Transformers ausente em vendor/Co-Transformers-main. "
            "Execute: python scripts/download_co_transformers_weights.py",
        )

    seg = resolve_co_transformers_segformer_pretrain()
    np_path = resolve_co_transformers_noiseprint()
    ckpt = resolve_co_transformers_checkpoint()
    missing: list[str] = []
    if seg is None:
        missing.append("mit_b3.pth (SegFormer-B3)")
    if np_path is None:
        missing.append("noiseprint.pth")
    if ckpt is None:
        missing.append("checkpoint treinado (co_transformers.pth ou checkpoint-*.pth)")

    if missing:
        return (
            False,
            f"Pesos Co-Transformers incompletos ({', '.join(missing)}). "
            "Execute: python scripts/download_co_transformers_weights.py",
        )

    try:
        _ensure_co_transformers_registered()
    except Exception as exc:
        return False, f"Falha ao carregar Co-Transformers: {exc}"

    return True, ""


_model_cache: dict[str, torch.nn.Module] = {}


def _build_model(device: torch.device) -> torch.nn.Module:
    from IMDLBenCo.registry import MODELS

    cache_key = f"co_transformers:{device.type}"
    if cache_key in _model_cache:
        return _model_cache[cache_key]

    _ensure_co_transformers_registered()
    seg = resolve_co_transformers_segformer_pretrain()
    np_path = resolve_co_transformers_noiseprint()
    ckpt_path = resolve_co_transformers_checkpoint()
    if not all([seg, np_path, ckpt_path]):
        raise RuntimeError("Pesos Co-Transformers incompletos.")

    try:
        model_cls = MODELS.get(MODEL_REGISTRY_NAME)
    except KeyError as exc:
        raise RuntimeError(f"Modelo {MODEL_REGISTRY_NAME} nao registrado no IMDLBenCo.") from exc
    if model_cls is None:
        raise RuntimeError(f"Modelo {MODEL_REGISTRY_NAME} nao registrado no IMDLBenCo.")

    model = model_cls(
        segformer_pretrain_path=str(seg),
        noiseprint_path=str(np_path),
    )
    state = _load_checkpoint_state(ckpt_path)
    model.load_state_dict(state, strict=False)
    model = model.to(device)
    model.eval()
    _model_cache[cache_key] = model
    return model


def _infer_tensor(evidence_path: str, *, device: torch.device) -> tuple[np.ndarray, np.ndarray, tuple[int, int]]:
    spec = get_method("co_transformers")
    if spec is None:
        raise RuntimeError("Metodo co_transformers nao catalogado.")

    batch = preprocess_single_image(evidence_path, spec)
    model = _build_model(device)

    with torch.no_grad():
        image = batch.image.unsqueeze(0).to(device)
        mask = batch.mask.unsqueeze(0).to(device)
        edge_mask = batch.edge_mask.unsqueeze(0).to(device) if batch.edge_mask is not None else mask
        out = model(image=image, mask=mask, edge_mask=edge_mask)
        pred512 = out["pred_mask"][0, 0].detach().cpu().numpy()

    heatmap = postprocess_mask(pred512, batch)
    return heatmap, batch.original_rgb, batch.origin_shape


def _heatmap_to_pil(heatmap: np.ndarray) -> Image.Image:
    arr = np.clip(heatmap * 255.0, 0, 255).astype(np.uint8)
    return Image.fromarray(arr, mode="L")


def _overlay(original: np.ndarray, heatmap: np.ndarray, alpha: float = 0.45) -> Image.Image:
    import matplotlib.cm as cm

    colored = (cm.inferno(np.clip(heatmap, 0.0, 1.0))[..., :3] * 255).astype(np.uint8)
    base = original.astype(np.float32)
    over = colored.astype(np.float32)
    blended = (base * (1.0 - alpha) + over * alpha).astype(np.uint8)
    return Image.fromarray(blended, mode="RGB")


def run_co_transformers_official_analysis(
    evidence_path: str,
    *,
    threshold: float = 0.5,
    on_progress: ProgressFn = None,
) -> CoTransformersOfficialResult:
    from core.gpu_inference import release_gpu_memory, run_with_device_fallback

    ok, reason = official_runtime_ready()
    if not ok:
        raise RuntimeError(reason)

    _report(on_progress, 8, "Preparando Co-Transformers (AAAI 2026)")

    def _run(device: torch.device):
        _report(on_progress, 30, "Inferencia Co-Transformers")
        return _infer_tensor(evidence_path, device=device)

    try:
        (heatmap, original, origin_shape), device = run_with_device_fallback(
            _run,
            on_fallback=lambda: _model_cache.clear(),
        )
    finally:
        release_gpu_memory()
        _model_cache.clear()

    mean_score = float(np.mean(heatmap))
    mask_bin = (heatmap >= threshold).astype(np.uint8) * 255

    _report(on_progress, 90, "Gerando artefatos Co-Transformers")
    return CoTransformersOfficialResult(
        input_image=Image.fromarray(original, mode="RGB"),
        heatmap_image=_heatmap_to_pil(heatmap),
        overlay_image=_overlay(original, heatmap),
        mask_image=Image.fromarray(mask_bin, mode="L"),
        original_size=origin_shape,
        mean_score=mean_score,
        inference_device=device.type,
    )
