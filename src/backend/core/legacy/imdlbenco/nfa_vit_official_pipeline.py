"""NFA-ViT official inference (BR-Gen model_zoo + IMDLBenCo transforms)."""

from __future__ import annotations

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
    resolve_nfa_vit_checkpoint,
    resolve_nfa_vit_init_weight,
    vendor_root,
)

ProgressFn = Callable[[int, str], None] | None

VENDOR_DIR = "BR-Gen-main"
MODEL_REGISTRY_NAME = "NFA_ViT_modify1"


@dataclass
class NfaVitOfficialResult:
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


def nfa_vit_vendor_root() -> Path:
    return vendor_root() / VENDOR_DIR


@lru_cache(maxsize=1)
def _ensure_nfa_vit_registered() -> None:
    """Import BR-Gen NFA-ViT and register in IMDLBenCo MODELS."""
    vendor = str(nfa_vit_vendor_root().resolve())
    if not nfa_vit_vendor_root().is_dir():
        raise RuntimeError(f"Codigo BR-Gen ausente em vendor/{VENDOR_DIR}.")
    if vendor not in sys.path:
        sys.path.insert(0, vendor)
    import importlib

    import IMDLBenCo.model_zoo  # noqa: F401

    importlib.import_module("model_zoo.nfa_vit.nfa_vit")


def _load_checkpoint_state(ckpt_path: Path) -> dict:
    try:
        obj = torch.load(str(ckpt_path), map_location="cpu", weights_only=False)
    except TypeError:
        obj = torch.load(str(ckpt_path), map_location="cpu")
    if isinstance(obj, dict) and "model" in obj:
        return obj["model"]
    if isinstance(obj, dict):
        return obj
    raise RuntimeError(f"Checkpoint NFA-ViT invalido: {ckpt_path}")


def official_runtime_ready() -> tuple[bool, str]:
    try:
        import einops  # noqa: F401
    except ImportError as exc:
        return False, f"Dependencia einops ausente: {exc}. pip install einops"

    try:
        import IMDLBenCo  # noqa: F401
    except ImportError as exc:
        return False, f"Pacote imdlbenco ausente: {exc}"

    if not nfa_vit_vendor_root().is_dir():
        return (
            False,
            f"Repositorio BR-Gen ausente em vendor/{VENDOR_DIR}. "
            "Clone: https://github.com/clpbc/BR-Gen",
        )

    missing_init: list[str] = []
    for key in ("noiseprint", "seg_b0", "seg_b2"):
        if resolve_nfa_vit_init_weight(key) is None:
            missing_init.append(key)

    ckpt = resolve_nfa_vit_checkpoint()
    if missing_init or ckpt is None:
        parts: list[str] = []
        if missing_init:
            parts.append(f"init ausente: {', '.join(missing_init)}")
        if ckpt is None:
            parts.append("checkpoint BR-Gen ausente (nfa_vit_brgen.pth ou checkpoint-*.pth)")
        return (
            False,
            f"Pesos NFA-ViT incompletos ({'; '.join(parts)}). "
            "Execute: python scripts/download_nfa_vit_weights.py",
        )

    try:
        _ensure_nfa_vit_registered()
    except Exception as exc:
        return False, f"Falha ao carregar model_zoo NFA-ViT: {exc}"

    return True, ""


_model_cache: dict[str, torch.nn.Module] = {}


def _build_model(device: torch.device) -> torch.nn.Module:
    from IMDLBenCo.registry import MODELS

    cache_key = f"nfa_vit:{device.type}"
    if cache_key in _model_cache:
        return _model_cache[cache_key]

    _ensure_nfa_vit_registered()
    np_path = resolve_nfa_vit_init_weight("noiseprint")
    b0_path = resolve_nfa_vit_init_weight("seg_b0")
    b2_path = resolve_nfa_vit_init_weight("seg_b2")
    ckpt_path = resolve_nfa_vit_checkpoint()
    if not all([np_path, b0_path, b2_path, ckpt_path]):
        raise RuntimeError("Pesos NFA-ViT incompletos.")

    model_cls = MODELS.get(MODEL_REGISTRY_NAME)
    if model_cls is None:
        raise RuntimeError(f"Modelo {MODEL_REGISTRY_NAME} nao registrado no IMDLBenCo.")

    model = model_cls(
        np_pretrain_weights=str(np_path),
        seg_b0_pretrain_weights=str(b0_path),
        seg_b2_pretrain_weights=str(b2_path),
    )
    state = _load_checkpoint_state(ckpt_path)
    model.load_state_dict(state, strict=False)
    model = model.to(device)
    model.eval()
    _model_cache[cache_key] = model
    return model


def _infer_tensor(evidence_path: str, *, device: torch.device) -> tuple[np.ndarray, np.ndarray, tuple[int, int]]:
    spec = get_method("nfa_vit")
    if spec is None:
        raise RuntimeError("Metodo nfa_vit nao catalogado.")

    batch = preprocess_single_image(evidence_path, spec)
    model = _build_model(device)

    with torch.no_grad():
        image = batch.image.unsqueeze(0).to(device)
        mask = batch.mask.unsqueeze(0).to(device)
        label = batch.label.to(device)
        out = model(image=image, mask=mask, label=label)
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


def run_nfa_vit_official_analysis(
    evidence_path: str,
    *,
    threshold: float = 0.5,
    on_progress: ProgressFn = None,
) -> NfaVitOfficialResult:
    from core.gpu_inference import release_gpu_memory, run_with_device_fallback

    ok, reason = official_runtime_ready()
    if not ok:
        raise RuntimeError(reason)

    _report(on_progress, 8, "Preparando NFA-ViT (BR-Gen)")

    def _run(device: torch.device):
        _report(on_progress, 30, "Inferencia NFA-ViT")
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

    _report(on_progress, 90, "Gerando artefatos NFA-ViT")
    return NfaVitOfficialResult(
        input_image=Image.fromarray(original, mode="RGB"),
        heatmap_image=_heatmap_to_pil(heatmap),
        overlay_image=_overlay(original, heatmap),
        mask_image=Image.fromarray(mask_bin, mode="L"),
        original_size=origin_shape,
        mean_score=mean_score,
        inference_device=device.type,
    )
