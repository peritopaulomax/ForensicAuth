"""DINOv3-IML official inference (ViT-L + LoRA r=32, CAT protocol).

Reference: https://github.com/Irennnne/DINOv3-IML
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable, Type
from unittest.mock import patch

import numpy as np
import torch
from PIL import Image

from core.legacy.imdlbenco.imdlbenco_catalog import get_method
from core.legacy.imdlbenco.imdlbenco_preprocess import postprocess_mask, preprocess_single_image
from core.legacy.imdlbenco.imdlbenco_runtime import (
    dinov3_backbone_repo,
    dinov3_iml_vendor_root,
    resolve_dinov3_iml_checkpoint,
)

ProgressFn = Callable[[int, str], None] | None

LORA_RANK = 32
LORA_ALPHA = 64.0
MODEL_TYPE = "dinov3_vitl16"
IMAGE_SIZE = 512


@dataclass
class Dinov3ImlOfficialResult:
    input_image: Image.Image
    heatmap_image: Image.Image
    overlay_image: Image.Image
    mask_image: Image.Image
    original_size: tuple[int, int]
    mean_score: float
    inference_device: str
    lora_rank: int
    gpu_fallback_reason: str | None = None
    gpu_fallback_warning: str | None = None


def _report(on_progress: ProgressFn, pct: int, label: str) -> None:
    if on_progress:
        on_progress(pct, label)


def _load_checkpoint_state(ckpt_path: Path) -> dict:
    try:
        obj = torch.load(str(ckpt_path), map_location="cpu", weights_only=False)
    except TypeError:
        obj = torch.load(str(ckpt_path), map_location="cpu")
    if isinstance(obj, dict) and "model" in obj:
        return obj["model"]
    if isinstance(obj, dict):
        return obj
    raise RuntimeError(f"Checkpoint DINOv3-IML invalido: {ckpt_path}")


def _hub_load_backbone_uninitialized(repo: str, name: str, *args, source: str = "local", weights=None, **kwargs):
    """Build DINOv3 backbone without downloading pretrained weights (checkpoint carries full state)."""
    if source != "local":
        raise RuntimeError("DINOv3-IML requer repositorio local em vendor/dinov3")
    repo_path = Path(repo).resolve()
    if str(repo_path) not in sys.path:
        sys.path.insert(0, str(repo_path))
    from dinov3.hub.backbones import dinov3_vitb16, dinov3_vitl16, dinov3_vits16

    factories = {
        "dinov3_vitl16": dinov3_vitl16,
        "dinov3_vits16": dinov3_vits16,
        "dinov3_vitb16": dinov3_vitb16,
    }
    factory = factories.get(name)
    if factory is None:
        raise ValueError(f"Modelo DINOv3 nao suportado: {name}")
    return factory(pretrained=False)


def official_runtime_ready() -> tuple[bool, str]:
    try:
        import peft  # noqa: F401
    except ImportError as exc:
        return False, f"Dependencia peft ausente: {exc}. pip install peft"

    if not dinov3_iml_vendor_root().is_dir():
        return (
            False,
            "Repositorio DINOv3-IML ausente em vendor/DINOv3-IML. "
            "Execute: python scripts/download_dinov3_iml_weights.py",
        )

    if not dinov3_backbone_repo().is_dir():
        return (
            False,
            "Backbone DINOv3 ausente em vendor/dinov3. "
            "Execute: python scripts/download_dinov3_iml_weights.py",
        )

    ckpt = resolve_dinov3_iml_checkpoint()
    if ckpt is None:
        return (
            False,
            "Checkpoint ViT-L LoRA r=32 ausente (cat_vitl_lora_r32.pth ou checkpoint-*.pth). "
            "Execute: python scripts/download_dinov3_iml_weights.py",
        )

    return True, ""


_model_cache: dict[str, torch.nn.Module] = {}
_DINOV3_FORENSICS_LORA_CLS: Type[torch.nn.Module] | None = None


def _load_dinov3_forensics_lora_class() -> Type[torch.nn.Module]:
    """Load vendor class without clashing with ForensicAuth ``models`` package."""
    global _DINOV3_FORENSICS_LORA_CLS
    if _DINOV3_FORENSICS_LORA_CLS is not None:
        return _DINOV3_FORENSICS_LORA_CLS

    vendor_root = dinov3_iml_vendor_root().resolve()
    module_path = vendor_root / "models" / "dinov3_forensics_lora.py"
    if not module_path.is_file():
        raise RuntimeError(f"Modulo DINOv3-IML ausente: {module_path}")

    module_name = "dinov3_iml_vendor.dinov3_forensics_lora"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Falha ao carregar spec de {module_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    cls = getattr(module, "DINOv3ForensicsLoRA", None)
    if cls is None:
        raise RuntimeError("DINOv3ForensicsLoRA nao encontrado no vendor DINOv3-IML")
    _DINOV3_FORENSICS_LORA_CLS = cls
    return cls


def _build_model(device: torch.device) -> torch.nn.Module:
    cache_key = f"dinov3_iml:{device.type}"
    if cache_key in _model_cache:
        return _model_cache[cache_key]

    ckpt_path = resolve_dinov3_iml_checkpoint()
    if ckpt_path is None:
        raise RuntimeError("Checkpoint DINOv3-IML ausente.")

    DINOv3ForensicsLoRA = _load_dinov3_forensics_lora_class()

    with patch("torch.hub.load", _hub_load_backbone_uninitialized):
        model = DINOv3ForensicsLoRA(
            dinov3_repo_path=str(dinov3_backbone_repo().resolve()),
            dinov3_weights_path="",
            dinov3_model_type=MODEL_TYPE,
            image_size=IMAGE_SIZE,
            lora_rank=LORA_RANK,
            lora_alpha=LORA_ALPHA,
        )

    state = _load_checkpoint_state(ckpt_path)
    model.load_state_dict(state, strict=False)
    model = model.to(device)
    model.eval()
    _model_cache[cache_key] = model
    return model


def _infer_tensor(evidence_path: str, *, device: torch.device) -> tuple[np.ndarray, np.ndarray, tuple[int, int]]:
    spec = get_method("dinov3_iml")
    if spec is None:
        raise RuntimeError("Metodo dinov3_iml nao catalogado.")

    batch = preprocess_single_image(evidence_path, spec)
    model = _build_model(device)

    with torch.no_grad():
        image = batch.image.unsqueeze(0).to(device)
        prob = model.predict(image)
        pred512 = prob[0, 0].detach().cpu().numpy()

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


def run_dinov3_iml_official_analysis(
    evidence_path: str,
    *,
    threshold: float = 0.5,
    on_progress: ProgressFn = None,
) -> Dinov3ImlOfficialResult:
    from core.gpu_inference import release_gpu_memory, run_with_device_fallback

    ok, reason = official_runtime_ready()
    if not ok:
        raise RuntimeError(reason)

    _report(on_progress, 8, "Preparando DINOv3-IML (ViT-L LoRA r=32)")

    def _run(device: torch.device):
        _report(on_progress, 30, "Inferencia DINOv3-IML")
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

    _report(on_progress, 90, "Gerando artefatos DINOv3-IML")
    return Dinov3ImlOfficialResult(
        input_image=Image.fromarray(original, mode="RGB"),
        heatmap_image=_heatmap_to_pil(heatmap),
        overlay_image=_overlay(original, heatmap),
        mask_image=Image.fromarray(mask_bin, mode="L"),
        original_size=origin_shape,
        mean_score=mean_score,
        inference_device=device.type,
        lora_rank=LORA_RANK,
    )
