"""CAT-Net official-style inference (jpegio DCT, full resolution, CAT_full_v2 weights)."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable
from unittest.mock import patch

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image

ProgressFn = Callable[[int, str], None] | None

DCT_CHANNELS = 1
DCT_T = 20


@dataclass
class CatNetOfficialResult:
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


def resolve_official_checkpoint() -> Path | None:
    from core.legacy.imdlbenco.imdlbenco_runtime import resolve_checkpoint

    return resolve_checkpoint("cat_net")


def official_runtime_ready() -> tuple[bool, str]:
    from core.legacy.imdlbenco.imdlbenco_runtime import resolve_cat_net_config

    try:
        import IMDLBenCo  # noqa: F401
        import jpegio  # noqa: F401
        import torch  # noqa: F401
    except ImportError as exc:
        return False, f"Dependencia CAT-Net ausente: {exc}"

    if resolve_official_checkpoint() is None:
        return (
            False,
            "Pesos CAT-Net ausentes. Execute: python scripts/download_imdlbenco_weights.py",
        )
    if not resolve_cat_net_config().is_file():
        return False, "Config CAT-Net ausente."
    return True, ""


def _get_jpeg_info(im_path: str) -> tuple[list[np.ndarray], list[np.ndarray]]:
    import jpegio

    jpeg = jpegio.read(str(im_path))
    num_channels = DCT_CHANNELS
    ci = jpeg.comp_info
    need_scale = [[ci[i].v_samp_factor, ci[i].h_samp_factor] for i in range(num_channels)]
    if num_channels == 3:
        if ci[0].v_samp_factor == ci[1].v_samp_factor == ci[2].v_samp_factor:
            need_scale[0][0] = need_scale[1][0] = need_scale[2][0] = 2
        if ci[0].h_samp_factor == ci[1].h_samp_factor == ci[2].h_samp_factor:
            need_scale[0][1] = need_scale[1][1] = need_scale[2][1] = 2
    else:
        need_scale[0][0] = 2
        need_scale[0][1] = 2

    dct_coef: list[np.ndarray] = []
    for i in range(num_channels):
        r, c = jpeg.coef_arrays[i].shape
        coef_view = jpeg.coef_arrays[i].reshape(r // 8, 8, c // 8, 8).transpose(0, 2, 1, 3)
        if need_scale[i][0] == 1 and need_scale[i][1] == 1:
            out_arr = np.zeros((r * 2, c * 2))
            out_view = out_arr.reshape(r * 2 // 8, 8, c * 2 // 8, 8).transpose(0, 2, 1, 3)
            out_view[::2, ::2, :, :] = coef_view
            out_view[1::2, ::2, :, :] = coef_view
            out_view[::2, 1::2, :, :] = coef_view
            out_view[1::2, 1::2, :, :] = coef_view
        elif need_scale[i][0] == 1 and need_scale[i][1] == 2:
            out_arr = np.zeros((r * 2, c))
            out_view = out_arr.reshape(r * 2 // 8, 8, c // 8, 8).transpose(0, 2, 1, 3)
            out_view[::2, :, :, :] = coef_view
            out_view[1::2, :, :, :] = coef_view
        elif need_scale[i][0] == 2 and need_scale[i][1] == 1:
            out_arr = np.zeros((r, c * 2))
            out_view = out_arr.reshape(r // 8, 8, c * 2 // 8, 8).transpose(0, 2, 1, 3)
            out_view[:, ::2, :, :] = coef_view
            out_view[:, 1::2, :, :] = coef_view
        elif need_scale[i][0] == 2 and need_scale[i][1] == 2:
            out_arr = np.zeros((r, c))
            out_view = out_arr.reshape(r // 8, 8, c // 8, 8).transpose(0, 2, 1, 3)
            out_view[:, :, :, :] = coef_view
        else:
            raise KeyError("JPEG chroma subsampling nao suportado")
        dct_coef.append(out_arr)

    qtables = [jpeg.quant_tables[ci[i].quant_tbl_no].astype(np.float64) for i in range(num_channels)]
    return dct_coef, qtables


def _prepare_tensors_from_jpeg(jpeg_path: str) -> tuple[torch.Tensor, torch.Tensor, tuple[int, int]]:
    """Mirror CAT-Net arbitrary mode: full image padded to 8x8 grid, DCT from file."""
    img_rgb = np.array(Image.open(jpeg_path).convert("RGB"))
    origin_h, origin_w = img_rgb.shape[:2]
    crop_size = (-(-origin_h // 8) * 8, -(-origin_w // 8) * 8)

    if origin_h < crop_size[0] or origin_w < crop_size[1]:
        temp = np.full((max(origin_h, crop_size[0]), max(origin_w, crop_size[1]), 3), 127.5)
        temp[:origin_h, :origin_w] = img_rgb
        img_rgb = temp

    dct_coef, qtables = _get_jpeg_info(jpeg_path)
    max_h = max(crop_size[0], max(dct_coef[c].shape[0] for c in range(DCT_CHANNELS)))
    max_w = max(crop_size[1], max(dct_coef[c].shape[1] for c in range(DCT_CHANNELS)))
    for i in range(DCT_CHANNELS):
        temp = np.full((max_h, max_w), 0.0)
        temp[: dct_coef[i].shape[0], : dct_coef[i].shape[1]] = dct_coef[i]
        dct_coef[i] = temp

    s_r, s_c = 0, 0
    img_rgb = img_rgb[s_r : s_r + crop_size[0], s_c : s_c + crop_size[1]]
    for i in range(DCT_CHANNELS):
        dct_coef[i] = dct_coef[i][s_r : s_r + crop_size[0], s_c : s_c + crop_size[1]]

    t_rgb = (torch.tensor(img_rgb.transpose(2, 0, 1), dtype=torch.float32) - 127.5) / 127.5
    t_dct_coef = torch.tensor(np.stack(dct_coef, axis=0), dtype=torch.float32)
    t_dct_vol = torch.zeros(size=(DCT_T + 1, t_dct_coef.shape[1], t_dct_coef.shape[2]))
    t_dct_vol[0] += (t_dct_coef == 0).float().squeeze()
    for i in range(1, DCT_T):
        t_dct_vol[i] += (t_dct_coef == i).float().squeeze()
        t_dct_vol[i] += (t_dct_coef == -i).float().squeeze()
    t_dct_vol[DCT_T] += (t_dct_coef >= DCT_T).float().squeeze()
    t_dct_vol[DCT_T] += (t_dct_coef <= -DCT_T).float().squeeze()

    tensor = torch.cat([t_rgb, t_dct_vol], dim=0)
    qtable = torch.tensor(qtables[:DCT_CHANNELS], dtype=torch.float32)
    return tensor, qtable, (origin_h, origin_w)


def _build_model(cfg_path: Path):
    from IMDLBenCo.registry import MODELS

    with patch.object(torch.nn.Module, "cuda", lambda self, device=None: self):
        return MODELS.get("Cat_Net")(cfg_file=str(cfg_path))


@lru_cache(maxsize=2)
def _load_model(device_type: str):
    from core.legacy.imdlbenco.imdlbenco_runtime import resolve_cat_net_config

    ckpt = resolve_official_checkpoint()
    if ckpt is None:
        raise RuntimeError("Pesos CAT-Net ausentes")

    model = _build_model(resolve_cat_net_config())
    obj = torch.load(str(ckpt), map_location="cpu", weights_only=False)
    state = obj.get("state_dict") or obj.get("model") or obj
    model.model.load_state_dict(state, strict=False)
    device = torch.device(device_type)
    model = model.to(device)
    model.eval()
    return model


def _predict(tensor: torch.Tensor, qtable: torch.Tensor, device: torch.device) -> np.ndarray:
    model = _load_model(device.type)
    stacked = tensor.unsqueeze(0).to(device)
    qtables = qtable.unsqueeze(0).unsqueeze(1).to(device)

    with torch.no_grad():
        outputs = model.model(stacked.float(), qtables.float())
        pred = F.softmax(outputs, dim=1)[:, 1].unsqueeze(1)
        pred = F.interpolate(pred, size=(tensor.shape[1], tensor.shape[2]), mode="bicubic")
    return pred[0, 0].detach().cpu().numpy()


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


def _infer_official(evidence_path: str, device: torch.device) -> dict[str, np.ndarray | tuple[int, int]]:
    path = Path(evidence_path)
    work_path = str(path)
    temp_jpg: Path | None = None
    if path.suffix.lower() not in (".jpg", ".jpeg"):
        temp_jpg = path.parent / f"__catnet_temp_{path.stem}.jpg"
        Image.open(path).convert("RGB").save(temp_jpg, quality=100, subsampling=0)
        work_path = str(temp_jpg)

    try:
        tensor, qtable, origin_size = _prepare_tensors_from_jpeg(work_path)
        heatmap_full = _predict(tensor, qtable, device)
        oh, ow = origin_size
        heatmap = heatmap_full[:oh, :ow]
        original = np.array(Image.open(evidence_path).convert("RGB"))
        return {
            "heatmap": np.clip(heatmap.astype(np.float32), 0.0, 1.0),
            "original": original,
            "original_size": origin_size,
        }
    finally:
        if temp_jpg is not None and temp_jpg.is_file():
            temp_jpg.unlink(missing_ok=True)


def run_cat_net_official_analysis(
    evidence_path: str,
    *,
    threshold: float = 0.5,
    on_progress: ProgressFn = None,
) -> CatNetOfficialResult:
    from core.gpu_inference import (
        pop_gpu_fallback_reason,
        purge_foreign_gpu_model_caches,
        run_with_device_fallback,
    )

    ok, reason = official_runtime_ready()
    if not ok:
        raise RuntimeError(reason)

    _report(on_progress, 8, "Preparando CAT-Net (modo oficial)")

    gpu_fallback_reason: str | None = None
    gpu_fallback_warning: str | None = None

    try:
        purge_foreign_gpu_model_caches(include_trufor=True)

        def _run(device):
            return _infer_official(evidence_path, device)

        payload, device = run_with_device_fallback(_run, allow_cpu_fallback=True)
        gpu_fallback_reason = pop_gpu_fallback_reason()
        if device.type == "cpu" and gpu_fallback_reason:
            gpu_fallback_warning = (
                "VRAM insuficiente na GPU (CUDA OOM). "
                "Continuando em CPU — resultado equivalente, porém muito mais lento."
            )

        heatmap = payload["heatmap"]
        original = payload["original"]
        mean_score = float(np.mean(heatmap))
        mask_bin = (heatmap >= threshold).astype(np.uint8) * 255

        _report(on_progress, 92, "Gerando artefatos CAT-Net")
        return CatNetOfficialResult(
            input_image=Image.fromarray(original, mode="RGB"),
            heatmap_image=_heatmap_to_pil(heatmap),
            overlay_image=_overlay(original, heatmap),
            mask_image=Image.fromarray(mask_bin, mode="L"),
            original_size=payload["original_size"],
            mean_score=mean_score,
            inference_device=device.type,
            gpu_fallback_reason=gpu_fallback_reason,
            gpu_fallback_warning=gpu_fallback_warning,
        )
    finally:
        clear_model_cache()


def clear_model_cache() -> None:
    _load_model.cache_clear()
