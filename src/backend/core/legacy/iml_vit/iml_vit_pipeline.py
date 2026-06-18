"""IML-ViT inference pipeline — image manipulation localization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
from PIL import Image

from core.legacy.iml_vit.iml_vit_imports import (
    load_edge_generator_class,
    load_get_albu_transforms,
    load_iml_vit_model_class,
)
from core.legacy.iml_vit.iml_vit_runtime import (
    iml_vit_inference_device,
    resolve_iml_vit_checkpoint,
)

ProgressFn = Callable[[int, str], None] | None

_model_cache: dict[str, object] = {}


@dataclass
class ImlVitAnalysisResult:
    input_image: Image.Image
    heatmap_image: Image.Image
    overlay_image: Image.Image
    mask_image: Image.Image
    original_size: tuple[int, int]
    inference_size: tuple[int, int]
    mean_manipulation_score: float
    inference_device: str


def _report(on_progress: ProgressFn, pct: int, label: str) -> None:
    if on_progress:
        on_progress(pct, label)


def _heatmap_to_pil(heatmap: np.ndarray) -> Image.Image:
    arr = np.clip(heatmap * 255.0, 0, 255).astype(np.uint8)
    return Image.fromarray(arr, mode="L")


def _align_heatmap_to_original(heatmap: np.ndarray, original_shape: tuple[int, int]) -> np.ndarray:
    """Map the 1024x1024 inference window back to the full image canvas."""
    h, w = original_shape
    hh, ww = heatmap.shape[:2]
    if hh == h and ww == w:
        return heatmap.astype(np.float32)

    canvas = np.zeros((h, w), dtype=np.float32)
    copy_h = min(hh, h)
    copy_w = min(ww, w)
    canvas[:copy_h, :copy_w] = heatmap[:copy_h, :copy_w]
    return canvas


def _overlay_heatmap(original: np.ndarray, heatmap: np.ndarray, alpha: float = 0.45) -> Image.Image:
    import matplotlib.cm as cm

    colored = (cm.inferno(np.clip(heatmap, 0.0, 1.0))[..., :3] * 255).astype(np.uint8)
    base = original.astype(np.float32)
    over = colored.astype(np.float32)
    blended = (base * (1.0 - alpha) + over * alpha).astype(np.uint8)
    return Image.fromarray(blended, mode="RGB")


def _get_model(on_progress: ProgressFn):
    device = iml_vit_inference_device()
    cache_key = str(device)
    if cache_key in _model_cache:
        return _model_cache[cache_key]

    import torch

    iml_vit_model = load_iml_vit_model_class()
    ckpt = resolve_iml_vit_checkpoint()
    if ckpt is None:
        raise RuntimeError("Checkpoint IML-ViT nao encontrado")

    label = "GPU" if device.type == "cuda" else "CPU (lento)"
    _report(on_progress, 12, f"Carregando IML-ViT em {label}")

    model = iml_vit_model(vit_pretrain_path=None)
    try:
        checkpoint = torch.load(str(ckpt), map_location="cpu", weights_only=False)
    except TypeError:
        checkpoint = torch.load(str(ckpt), map_location="cpu")

    if isinstance(checkpoint, dict) and "model" in checkpoint:
        state = checkpoint["model"]
    else:
        state = checkpoint

    model.load_state_dict(state, strict=True)
    model = model.to(device)
    model.eval()
    _model_cache[cache_key] = model
    _report(on_progress, 22, f"Modelo IML-ViT pronto ({device.type})")
    return model


def _preprocess(evidence_path: str, edge_width: int = 7):
    import torch

    EdgeGenerator = load_edge_generator_class()
    get_albu_transforms = load_get_albu_transforms()

    img = Image.open(evidence_path).convert("RGB")
    w, h = img.size
    arr = np.array(img)
    gt_img = np.zeros((h, w), dtype=np.float32)
    masks_list = [gt_img]
    if edge_width:
        edge_gen = EdgeGenerator(edge_width)
        broaden = edge_gen(gt_img)[0][0]
        masks_list.append(broaden)

    padding_transform = get_albu_transforms(type_="pad", outputsize=1024)
    res = padding_transform(image=arr, masks=masks_list)
    tensor_img = res["image"]
    gt_mask = res["masks"][0].unsqueeze(0).float()
    edge_mask = res["masks"][1].unsqueeze(0).float() if edge_width else gt_mask.clone()
    shape = torch.tensor([h, w])
    return tensor_img, gt_mask, edge_mask, shape, arr


def run_iml_vit_analysis(
    evidence_path: str,
    *,
    threshold: float = 0.5,
    on_progress: ProgressFn = None,
) -> ImlVitAnalysisResult:
    """Run IML-ViT on one image path."""
    device = iml_vit_inference_device()
    _report(on_progress, 5, "Carregando evidencia")

    tensor_img, gt_mask, edge_mask, shape, original = _preprocess(evidence_path)
    input_preview = Image.fromarray(original, mode="RGB")
    original_size = (original.shape[0], original.shape[1])

    model = _get_model(on_progress)
    _report(on_progress, 30, "Executando IML-ViT")

    import torch

    with torch.no_grad():
        img = tensor_img.unsqueeze(0).to(device)
        gt = gt_mask.unsqueeze(0).to(device)
        edge = edge_mask.unsqueeze(0).to(device)
        _predict_loss, mask_pred, _edge_loss = model(img, gt, edge)
        output = mask_pred[0, 0, : int(shape[0]), : int(shape[1])].detach().cpu().numpy()

    heatmap_crop = np.clip(output.astype(np.float32), 0.0, 1.0)
    heatmap = _align_heatmap_to_original(heatmap_crop, original_size)
    mean_score = float(np.mean(heatmap_crop))
    mask_bin = (heatmap >= threshold).astype(np.uint8) * 255

    _report(on_progress, 88, "Gerando mapas na resolucao original")
    heatmap_img = _heatmap_to_pil(heatmap)
    mask_img = Image.fromarray(mask_bin, mode="L")
    overlay_img = _overlay_heatmap(original, heatmap)
    _report(on_progress, 95, "IML-ViT concluido")

    return ImlVitAnalysisResult(
        input_image=input_preview,
        heatmap_image=heatmap_img,
        overlay_image=overlay_img,
        mask_image=mask_img,
        original_size=original_size,
        inference_size=(1024, 1024),
        mean_manipulation_score=mean_score,
        inference_device=device.type,
    )
