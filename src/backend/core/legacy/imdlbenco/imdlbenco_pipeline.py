"""IMDL-BenCo hub inference — routes to native and ecosystem methods."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from unittest.mock import patch

import numpy as np
from PIL import Image

from core.gpu_inference import (
    evict_cache_keys_on_device,
    release_gpu_memory,
    run_with_device_fallback,
)
from core.legacy.imdlbenco.imdlbenco_catalog import get_method
from core.legacy.imdlbenco.imdlbenco_preprocess import postprocess_mask, preprocess_single_image
from core.legacy.imdlbenco.imdlbenco_runtime import (
    method_runtime_status,
    resolve_cat_net_config,
    resolve_checkpoint,
    resolve_objectformer_init,
    resolve_segformer_pretrain,
    resolve_trufor_config,
    resolve_uniformer_pretrain,
)

ProgressFn = Callable[[int, str], None] | None

_model_cache: dict[str, object] = {}


@dataclass
class ImdlBencoAnalysisResult:
    method_id: str
    method_name: str
    input_image: Image.Image
    heatmap_image: Image.Image
    score_map_image: Image.Image
    overlay_image: Image.Image
    mask_image: Image.Image
    confidence_image: Image.Image | None
    original_size: tuple[int, int]
    mean_score: float
    integrity_score: float | None
    inference_device: str
    inference_window_note: str | None
    gpu_fallback_reason: str | None = None
    gpu_fallback_warning: str | None = None


def _report(on_progress: ProgressFn, pct: int, label: str) -> None:
    if on_progress:
        on_progress(pct, label)


def _clear_gpu_model_cache() -> None:
    evict_cache_keys_on_device(_model_cache)
    release_gpu_memory()


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


def _align_top_left(heatmap: np.ndarray, original_shape: tuple[int, int]) -> tuple[np.ndarray, str | None]:
    h, w = original_shape
    hh, ww = heatmap.shape[:2]
    if hh == h and ww == w:
        return heatmap, None
    canvas = np.zeros((h, w), dtype=np.float32)
    copy_h = min(hh, h)
    copy_w = min(ww, w)
    canvas[:copy_h, :copy_w] = heatmap[:copy_h, :copy_w]
    note = (
        f"Janela de inferencia {hh}x{ww} no canto superior esquerdo; "
        "demais regioes sem predicao."
    )
    return canvas, note


@contextmanager
def _cpu_safe_torch_load():
    """Force torch.load onto CPU (checkpoints saved on CUDA break CPU-only hosts)."""
    import torch

    original = torch.load

    def patched_load(f, *args, map_location=None, **kwargs):
        if map_location is None:
            map_location = torch.device("cpu")
        try:
            return original(f, *args, map_location=map_location, **kwargs)
        except TypeError:
            kwargs.pop("weights_only", None)
            return original(f, *args, map_location=map_location, **kwargs)

    torch.load = patched_load
    try:
        yield
    finally:
        torch.load = original


def _build_trufor_for_inference(config_path: Path):
    """Instantiate TruFor for inference without phase-2 aux weight loading."""
    import torch.nn as nn
    from IMDLBenCo.model_zoo.trufor.cmx.builder_np_conf import myEncoderDecoder as confcmx
    from IMDLBenCo.model_zoo.trufor.config import _C as config
    from IMDLBenCo.model_zoo.trufor.config import update_config
    from IMDLBenCo.model_zoo.trufor.trufor import Trufor

    update_config(config, None, str(config_path))
    model = Trufor.__new__(Trufor)
    nn.Module.__init__(model)
    model.model = confcmx(cfg=config)
    model.phase = 3
    return model


def _load_checkpoint_state(ckpt_path: Path):
    import torch

    try:
        obj = torch.load(str(ckpt_path), map_location="cpu", weights_only=False)
    except TypeError:
        obj = torch.load(str(ckpt_path), map_location="cpu")
    if isinstance(obj, dict):
        if "model" in obj:
            return obj["model"]
        if "state_dict" in obj:
            return obj["state_dict"]
    return obj


def _build_cat_net(cfg_path: Path):
    import torch
    from IMDLBenCo.registry import MODELS

    with patch.object(torch.nn.Module, "cuda", lambda self, device=None: self):
        model = MODELS.get("Cat_Net")(cfg_file=str(cfg_path))
    return model


def _cat_net_predict(model, image, mask, dct_coef, qtables, device):
    import torch
    import torch.nn.functional as F

    img_rgb = torch.permute(image, (0, 2, 3, 1))
    t_rgb = (torch.permute(img_rgb, (0, 3, 1, 2)) - 127.5) / 127.5
    dct_coef = dct_coef.to(device)
    t = 20
    t_dct_vol = torch.zeros(
        size=(dct_coef.shape[0], t + 1, dct_coef.shape[1], dct_coef.shape[2]),
        device=device,
    )
    t_dct_vol[:, 0] += (dct_coef == 0).float()
    for i in range(1, t):
        t_dct_vol[:, i] += (dct_coef == i).float()
        t_dct_vol[:, i] += (dct_coef == -i).float()
    t_dct_vol[:, t] += (dct_coef >= t).float()
    t_dct_vol[:, t] += (dct_coef <= -t).float()
    tensor = torch.cat([t_rgb.to(device), t_dct_vol], dim=1)
    qtables = qtables.unsqueeze(1).to(device)
    outputs = model.model(tensor.float(), qtables.float())
    pred = F.softmax(outputs, dim=1)[:, 1].unsqueeze(1)
    pred = F.interpolate(pred, size=(image.shape[2], image.shape[3]), mode="bicubic")
    return pred


def _load_native_model(method_id: str, device, *, mesorch_variant: str = "standard"):
    import IMDLBenCo.model_zoo  # noqa: F401 — register models
    import torch
    from IMDLBenCo.registry import MODELS

    cache_key = (
        f"{method_id}:{mesorch_variant}:{device}"
        if method_id == "mesorch"
        else f"{method_id}:{device}"
    )
    if cache_key in _model_cache:
        return _model_cache[cache_key]

    ckpt = resolve_checkpoint(method_id, mesorch_variant=mesorch_variant)
    state = _load_checkpoint_state(ckpt) if ckpt else None

    if method_id == "mesorch":
        seg = resolve_segformer_pretrain()
        model = MODELS.get("Mesorch")(
            seg_pretrain_path=str(seg) if seg else None,
            conv_pretrain=True,
        )
        model.load_state_dict(state, strict=False)
    elif method_id == "sparse_vit":
        uniformer = resolve_uniformer_pretrain()
        model = MODELS.get("SparseViT")(
            img_size=512,
            pretrained_path=str(uniformer) if uniformer else None,
        )
        model.load_state_dict(state, strict=False)
    elif method_id == "trufor":
        with _cpu_safe_torch_load():
            model = _build_trufor_for_inference(resolve_trufor_config())
        model.load_state_dict(state, strict=False)
    elif method_id == "cat_net":
        model = _build_cat_net(resolve_cat_net_config())
        state = _load_checkpoint_state(ckpt)
        model.model.load_state_dict(state, strict=False)
    elif method_id == "objectformer":
        init_path = resolve_objectformer_init()
        with _cpu_safe_torch_load():
            model = MODELS.get("ObjectFormer")(
                init_weight_path=str(init_path) if init_path else None,
            )
        model.load_state_dict(state, strict=False)
    else:
        raise RuntimeError(f"Modelo nativo nao suportado: {method_id}")

    model = model.to(device)
    model.eval()
    _model_cache[cache_key] = model
    return model


def _run_native_benco(
    evidence_path: str,
    method_id: str,
    *,
    mesorch_variant: str = "standard",
    on_progress: ProgressFn,
    device,
) -> tuple[np.ndarray, np.ndarray, str | None]:
    spec = get_method(method_id)
    if spec is None:
        raise ValueError("metodo invalido")

    batch = preprocess_single_image(evidence_path, spec)
    model = _load_native_model(method_id, device, mesorch_variant=mesorch_variant)
    _report(on_progress, 35, f"Inferencia {spec.name}")

    import torch

    try:
        with torch.no_grad():
            image = batch.image.unsqueeze(0).to(device)
            mask = batch.mask.unsqueeze(0).to(device)

            if method_id == "cat_net":
                if batch.dct_coef is None or batch.qtables is None:
                    raise RuntimeError("Features JPEG ausentes para CAT-Net.")
                pred = _cat_net_predict(model, image, mask, batch.dct_coef, batch.qtables, device)
                pred_np = pred[0, 0].detach().cpu().numpy()
            elif method_id == "trufor":
                import torch.nn.functional as F

                pred_mask, _, _, _ = model.model(image)
                pred_mask = F.softmax(pred_mask, dim=1)[:, -1].unsqueeze(1)
                pred_np = pred_mask[0, 0].detach().cpu().numpy()
            else:
                if method_id in ("mesorch", "objectformer"):
                    label = batch.label.to(device)
                    out = model(image=image, mask=mask, label=label)
                else:
                    out = model(image=image, mask=mask)
                pred_np = out["pred_mask"][0, 0].detach().cpu().numpy()
    finally:
        release_gpu_memory(model)

    heatmap = postprocess_mask(pred_np, batch)
    note = None
    if spec.use_padding and max(batch.origin_shape) > spec.image_size:
        heatmap, note = _align_top_left(heatmap, batch.origin_shape)
    return heatmap, batch.original_rgb, note


def _run_ecosystem_placeholder(method_id: str) -> None:
    status, reason = method_runtime_status(method_id)
    if status != "ready":
        raise RuntimeError(reason or f"Metodo {method_id} indisponivel.")
    raise RuntimeError(
        f"Inferencia para {method_id} ainda nao integrada neste build. "
        "Clone o repositorio em vendor/ e adicione os pesos."
    )


def run_imdlbenco_analysis(
    evidence_path: str,
    *,
    method: str,
    threshold: float = 0.5,
    mesorch_variant: str = "standard",
    on_progress: ProgressFn = None,
) -> ImdlBencoAnalysisResult:
    spec = get_method(method)
    if spec is None:
        raise ValueError(f"Metodo IMDL-BenCo desconhecido: {method}")

    status, reason = method_runtime_status(method)
    if status != "ready":
        raise RuntimeError(reason or f"{spec.name} indisponivel")

    _report(on_progress, 8, f"Preparando {spec.name}")

    if method == "miml_apscnet":
        from core.legacy.imdlbenco.miml_official_pipeline import run_miml_apscnet_analysis

        official = run_miml_apscnet_analysis(
            evidence_path,
            threshold=threshold,
            on_progress=on_progress,
        )
        _report(on_progress, 90, "Gerando artefatos")
        return ImdlBencoAnalysisResult(
            method_id=method,
            method_name=spec.name,
            input_image=official.input_image,
            heatmap_image=official.heatmap_image,
            score_map_image=official.heatmap_image,
            overlay_image=official.overlay_image,
            mask_image=official.mask_image,
            confidence_image=None,
            original_size=official.original_size,
            mean_score=official.mean_score,
            integrity_score=None,
            inference_device=official.inference_device,
            inference_window_note=None,
            gpu_fallback_reason=official.gpu_fallback_reason,
            gpu_fallback_warning=official.gpu_fallback_warning,
        )

    if method == "dinov3_iml":
        from core.legacy.imdlbenco.dinov3_iml_official_pipeline import run_dinov3_iml_official_analysis

        official = run_dinov3_iml_official_analysis(
            evidence_path,
            threshold=threshold,
            on_progress=on_progress,
        )
        _report(on_progress, 90, "Gerando artefatos")
        return ImdlBencoAnalysisResult(
            method_id=method,
            method_name=spec.name,
            input_image=official.input_image,
            heatmap_image=official.heatmap_image,
            score_map_image=official.heatmap_image,
            overlay_image=official.overlay_image,
            mask_image=official.mask_image,
            confidence_image=None,
            original_size=official.original_size,
            mean_score=official.mean_score,
            integrity_score=None,
            inference_device=official.inference_device,
            inference_window_note=None,
            gpu_fallback_reason=official.gpu_fallback_reason,
            gpu_fallback_warning=official.gpu_fallback_warning,
        )

    if method == "nfa_vit":
        from core.legacy.imdlbenco.nfa_vit_official_pipeline import run_nfa_vit_official_analysis

        official = run_nfa_vit_official_analysis(
            evidence_path,
            threshold=threshold,
            on_progress=on_progress,
        )
        _report(on_progress, 90, "Gerando artefatos")
        return ImdlBencoAnalysisResult(
            method_id=method,
            method_name=spec.name,
            input_image=official.input_image,
            heatmap_image=official.heatmap_image,
            score_map_image=official.heatmap_image,
            overlay_image=official.overlay_image,
            mask_image=official.mask_image,
            confidence_image=None,
            original_size=official.original_size,
            mean_score=official.mean_score,
            integrity_score=None,
            inference_device=official.inference_device,
            inference_window_note=None,
            gpu_fallback_reason=official.gpu_fallback_reason,
            gpu_fallback_warning=official.gpu_fallback_warning,
        )

    if method == "co_transformers":
        from core.legacy.imdlbenco.co_transformers_official_pipeline import (
            run_co_transformers_official_analysis,
        )

        official = run_co_transformers_official_analysis(
            evidence_path,
            threshold=threshold,
            on_progress=on_progress,
        )
        _report(on_progress, 90, "Gerando artefatos")
        return ImdlBencoAnalysisResult(
            method_id=method,
            method_name=spec.name,
            input_image=official.input_image,
            heatmap_image=official.heatmap_image,
            score_map_image=official.heatmap_image,
            overlay_image=official.overlay_image,
            mask_image=official.mask_image,
            confidence_image=None,
            original_size=official.original_size,
            mean_score=official.mean_score,
            integrity_score=None,
            inference_device=official.inference_device,
            inference_window_note=None,
            gpu_fallback_reason=official.gpu_fallback_reason,
            gpu_fallback_warning=official.gpu_fallback_warning,
        )

    if spec.tier == "ecosystem":
        _run_ecosystem_placeholder(method)

    if method == "trufor":
        from core.legacy.imdlbenco.trufor_official_pipeline import run_trufor_official_analysis

        official = run_trufor_official_analysis(
            evidence_path,
            threshold=threshold,
            on_progress=on_progress,
        )
        _report(on_progress, 90, "Gerando artefatos")
        return ImdlBencoAnalysisResult(
            method_id=method,
            method_name=spec.name,
            input_image=official.input_image,
            heatmap_image=official.heatmap_image,
            score_map_image=official.score_map_image,
            overlay_image=official.overlay_image,
            mask_image=official.mask_image,
            confidence_image=official.confidence_image,
            original_size=official.original_size,
            mean_score=official.mean_localization_score,
            integrity_score=official.integrity_score,
            inference_device=official.inference_device,
            inference_window_note=None,
            gpu_fallback_reason=official.gpu_fallback_reason,
            gpu_fallback_warning=official.gpu_fallback_warning,
        )

    if method == "cat_net":
        from core.legacy.imdlbenco.cat_net_official_pipeline import run_cat_net_official_analysis

        official = run_cat_net_official_analysis(
            evidence_path,
            threshold=threshold,
            on_progress=on_progress,
        )
        _report(on_progress, 90, "Gerando artefatos")
        return ImdlBencoAnalysisResult(
            method_id=method,
            method_name=spec.name,
            input_image=official.input_image,
            heatmap_image=official.heatmap_image,
            score_map_image=official.heatmap_image,
            overlay_image=official.overlay_image,
            mask_image=official.mask_image,
            confidence_image=None,
            original_size=official.original_size,
            mean_score=official.mean_score,
            integrity_score=None,
            inference_device=official.inference_device,
            inference_window_note=None,
            gpu_fallback_reason=official.gpu_fallback_reason,
            gpu_fallback_warning=official.gpu_fallback_warning,
        )

    if method == "mesorch":
        from core.legacy.imdlbenco.mesorch_official_pipeline import run_mesorch_official_analysis

        official = run_mesorch_official_analysis(
            evidence_path,
            threshold=threshold,
            mesorch_variant=mesorch_variant,
            on_progress=on_progress,
        )
        _report(on_progress, 90, "Gerando artefatos")
        return ImdlBencoAnalysisResult(
            method_id=method,
            method_name=spec.name,
            input_image=official.input_image,
            heatmap_image=official.heatmap_image,
            score_map_image=official.heatmap_image,
            overlay_image=official.overlay_image,
            mask_image=official.mask_image,
            confidence_image=None,
            original_size=official.original_size,
            mean_score=official.mean_score,
            integrity_score=None,
            inference_device=official.inference_device,
            inference_window_note=None,
            gpu_fallback_reason=official.gpu_fallback_reason,
            gpu_fallback_warning=official.gpu_fallback_warning,
        )

    def _run(device):
        return _run_native_benco(
            evidence_path,
            method,
            mesorch_variant=mesorch_variant,
            on_progress=on_progress,
            device=device,
        )

    try:
        (heatmap, original, window_note), device = run_with_device_fallback(
            _run,
            on_fallback=_clear_gpu_model_cache,
        )
    finally:
        from core.gpu_residency import release_imdl_cache_if_needed, touch_lru

        touch_lru("imdlbenco")
        release_imdl_cache_if_needed()

    mean_score = float(np.mean(heatmap))
    mask_bin = (heatmap >= threshold).astype(np.uint8) * 255

    _report(on_progress, 90, "Gerando artefatos")
    return ImdlBencoAnalysisResult(
        method_id=method,
        method_name=spec.name,
        input_image=Image.fromarray(original, mode="RGB"),
        heatmap_image=_heatmap_to_pil(heatmap),
        score_map_image=_heatmap_to_pil(heatmap),
        overlay_image=_overlay(original, heatmap),
        mask_image=Image.fromarray(mask_bin, mode="L"),
        confidence_image=None,
        original_size=(original.shape[0], original.shape[1]),
        mean_score=mean_score,
        integrity_score=None,
        inference_device=device.type,
        inference_window_note=window_note,
    )
