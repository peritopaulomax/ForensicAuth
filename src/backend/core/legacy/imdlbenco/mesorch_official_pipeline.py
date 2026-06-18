"""Mesorch official-style inference (512 resize, IMDLBenCo transforms, Mesorch + Mesorch-P)."""

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
    MESORCH_VARIANTS,
    resolve_mesorch_checkpoint,
    resolve_segformer_pretrain,
)

ProgressFn = Callable[[int, str], None] | None

VENDOR_ROOT = Path(__file__).resolve().parents[5] / "vendor" / "Mesorch"
IMAGE_SIZE = 512


@dataclass
class MesorchOfficialResult:
    input_image: Image.Image
    heatmap_image: Image.Image
    overlay_image: Image.Image
    mask_image: Image.Image
    original_size: tuple[int, int]
    mean_score: float
    inference_device: str
    mesorch_variant: str
    gpu_fallback_reason: str | None = None
    gpu_fallback_warning: str | None = None


def _report(on_progress: ProgressFn, pct: int, label: str) -> None:
    if on_progress:
        on_progress(pct, label)


def mesorch_vendor_root() -> Path:
    return VENDOR_ROOT


@lru_cache(maxsize=1)
def _ensure_mesorch_p_registered() -> None:
    vendor = str(mesorch_vendor_root().resolve())
    if not mesorch_vendor_root().is_dir():
        raise RuntimeError("Codigo Mesorch-P ausente em vendor/Mesorch.")
    if vendor not in sys.path:
        sys.path.insert(0, vendor)
    import importlib

    importlib.import_module("mesorch_p")


def _load_checkpoint_state(ckpt_path: Path) -> dict:
    try:
        obj = torch.load(str(ckpt_path), map_location="cpu", weights_only=False)
    except TypeError:
        obj = torch.load(str(ckpt_path), map_location="cpu")
    if isinstance(obj, dict) and "model" in obj:
        return obj["model"]
    if isinstance(obj, dict) and "state_dict" in obj:
        return obj["state_dict"]
    if isinstance(obj, dict):
        return obj
    raise RuntimeError(f"Checkpoint Mesorch invalido: {ckpt_path}")


def official_runtime_ready(*, mesorch_variant: str = "standard") -> tuple[bool, str]:
    if mesorch_variant not in MESORCH_VARIANTS:
        return False, f"Variante Mesorch invalida: {mesorch_variant}"
    try:
        import IMDLBenCo  # noqa: F401
        import timm  # noqa: F401
    except ImportError as exc:
        return False, f"Dependencia Mesorch ausente: {exc}"

    ckpt = resolve_mesorch_checkpoint(mesorch_variant)
    if ckpt is None:
        fname = MESORCH_VARIANTS[mesorch_variant]
        return (
            False,
            f"Pesos Mesorch ausentes ({fname}). Execute: python scripts/download_imdlbenco_weights.py",
        )

    if mesorch_variant == "mesorch_p" and not mesorch_vendor_root().is_dir():
        return (
            False,
            "Codigo Mesorch-P ausente em vendor/Mesorch (mesorch_p.py).",
        )
    return True, ""


_model_cache: dict[str, torch.nn.Module] = {}


def _build_model(mesorch_variant: str, device: torch.device) -> torch.nn.Module:
    import IMDLBenCo.model_zoo  # noqa: F401 — register Mesorch
    from IMDLBenCo.registry import MODELS

    cache_key = f"{mesorch_variant}:{device.type}"
    if cache_key in _model_cache:
        return _model_cache[cache_key]

    ckpt = resolve_mesorch_checkpoint(mesorch_variant)
    if ckpt is None:
        raise RuntimeError("Checkpoint Mesorch ausente.")

    seg = resolve_segformer_pretrain()
    seg_path = str(seg) if seg else None

    if mesorch_variant == "mesorch_p":
        _ensure_mesorch_p_registered()
        model = MODELS.get("Mesorch_P")(
            seg_pretrain_path=seg_path,
            conv_pretrain=False,
            image_size=IMAGE_SIZE,
        )
    else:
        model = MODELS.get("Mesorch")(
            seg_pretrain_path=seg_path,
            conv_pretrain=False,
        )

    state = _load_checkpoint_state(ckpt)
    model.load_state_dict(state, strict=False)
    model = model.to(device)
    model.eval()
    _model_cache[cache_key] = model
    return model


def _infer_tensor(
    evidence_path: str,
    *,
    mesorch_variant: str,
    device: torch.device,
) -> tuple[np.ndarray, np.ndarray, tuple[int, int]]:
    spec = get_method("mesorch")
    if spec is None:
        raise RuntimeError("Metodo mesorch nao catalogado.")

    batch = preprocess_single_image(evidence_path, spec)
    model = _build_model(mesorch_variant, device)

    with torch.no_grad():
        image = batch.image.unsqueeze(0).to(device)
        mask = batch.mask.unsqueeze(0).to(device)
        if mesorch_variant == "mesorch_p":
            out = model(image=image, mask=mask)
        else:
            out = model(image=image, mask=mask, label=batch.label.to(device))
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


def run_mesorch_official_analysis(
    evidence_path: str,
    *,
    threshold: float = 0.5,
    mesorch_variant: str = "standard",
    on_progress: ProgressFn = None,
) -> MesorchOfficialResult:
    from core.gpu_inference import release_gpu_memory, run_with_device_fallback

    ok, reason = official_runtime_ready(mesorch_variant=mesorch_variant)
    if not ok:
        raise RuntimeError(reason)

    _report(on_progress, 8, "Preparando Mesorch")

    def _run(device: torch.device):
        _report(on_progress, 30, "Inferencia Mesorch")
        return _infer_tensor(evidence_path, mesorch_variant=mesorch_variant, device=device)

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

    _report(on_progress, 90, "Gerando artefatos")
    return MesorchOfficialResult(
        input_image=Image.fromarray(original, mode="RGB"),
        heatmap_image=_heatmap_to_pil(heatmap),
        overlay_image=_overlay(original, heatmap),
        mask_image=Image.fromarray(mask_bin, mode="L"),
        original_size=origin_shape,
        mean_score=mean_score,
        inference_device=device.type,
        mesorch_variant=mesorch_variant,
    )
