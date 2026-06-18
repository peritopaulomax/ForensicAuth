"""GRIP-UNINA blind localization (noiseprint_blind) without TensorFlow extraction."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

GRIP_ROOT = Path(__file__).resolve().parents[5] / "vendor" / "grip-unina-noiseprint"


@dataclass
class BlindLocalizationResult:
    mapp: np.ndarray | None
    mapp_float: np.ndarray | None
    heatmap_uint8: np.ndarray | None
    valid: np.ndarray | None
    valid_mask_full: np.ndarray | None
    valid_pixel_fraction: float | None
    range0: np.ndarray | None
    range1: np.ndarray | None
    imgsize: np.ndarray | None
    other: dict[str, Any]
    status: str


def _patch_pillow_jpeg_qtables() -> None:
    import PIL.JpegImagePlugin as jpeg_plugin

    if hasattr(jpeg_plugin, "convert_dict_qtables"):
        return

    def convert_dict_qtables(qtables):
        return qtables

    jpeg_plugin.convert_dict_qtables = convert_dict_qtables


@lru_cache(maxsize=1)
def _ensure_grip_imports():
    _patch_pillow_jpeg_qtables()
    root = str(GRIP_ROOT.resolve())
    if root not in sys.path:
        sys.path.insert(0, root)
    from noiseprint.post_em import EMgu_img, getSpamFromNoiseprint
    from noiseprint.utility.utilityRead import resizeMapWithPadding

    return getSpamFromNoiseprint, EMgu_img, resizeMapWithPadding


def noiseprint_blind_post(res: np.ndarray, img_gray: np.ndarray) -> BlindLocalizationResult:
    """Faithful GRIP-UNINA blind localization on a precomputed noiseprint map."""
    get_spam, em_gu_img, resize_map = _ensure_grip_imports()
    spam, valid, range0, range1, imgsize = get_spam(res, img_gray)

    if np.sum(valid) < 50:
        valid_full, valid_frac = gen_valid_mask_full(valid, range0, range1, imgsize, resize_map)
        return BlindLocalizationResult(
            mapp=None,
            mapp_float=None,
            heatmap_uint8=None,
            valid=valid,
            valid_mask_full=valid_full,
            valid_pixel_fraction=valid_frac,
            range0=range0,
            range1=range1,
            imgsize=imgsize,
            other={},
            status="too_small_or_uniform",
        )

    mapp, other = em_gu_img(
        spam,
        valid,
        extFeat=range(32),
        seed=0,
        maxIter=100,
        replicates=10,
        outliersNlogl=42,
    )
    mapp_float = gen_mapp_float(mapp, valid, range0, range1, imgsize, resize_map)
    heatmap_uint8 = gen_mapp_uint8(mapp, valid, range0, range1, imgsize, resize_map)
    valid_full, valid_frac = gen_valid_mask_full(valid, range0, range1, imgsize, resize_map)
    return BlindLocalizationResult(
        mapp=mapp,
        mapp_float=mapp_float,
        heatmap_uint8=heatmap_uint8,
        valid=valid,
        valid_mask_full=valid_full,
        valid_pixel_fraction=valid_frac,
        range0=range0,
        range1=range1,
        imgsize=imgsize,
        other=other,
        status="ok",
    )


def gen_valid_mask_full(
    valid: np.ndarray,
    range0: np.ndarray,
    range1: np.ndarray,
    imgsize: np.ndarray,
    resize_map,
) -> tuple[np.ndarray, float]:
    """Upsample SPAM-grid valid mask to full image size (GRIP-UNINA resizeMapWithPadding)."""
    if valid is None or valid.size == 0:
        return np.zeros(tuple(int(x) for x in imgsize), dtype=np.float32), 0.0
    valid_f = valid.astype(np.float32)
    full = resize_map(valid_f, range0, range1, imgsize)
    full = np.clip(full, 0.0, 1.0)
    fraction = float(np.mean(full >= 0.5)) if full.size else 0.0
    return full, fraction


def valid_mask_image(valid_mask_full: np.ndarray) -> Image.Image:
    """Grayscale mask: white = pixel confiavel para localizacao blind."""
    channel = (np.clip(valid_mask_full, 0.0, 1.0) * 255.0).astype(np.uint8)
    return Image.fromarray(channel, mode="L")


def overlay_valid_mask(original_rgb: np.ndarray, valid_mask_full: np.ndarray, alpha: float = 0.45) -> Image.Image:
    """Tint unreliable (invalid) regions in red over the input image."""
    base = original_rgb.astype(np.float32)
    invalid = valid_mask_full < 0.5
    tint = np.zeros_like(base)
    tint[..., 0] = 220.0
    tint[..., 1] = 60.0
    tint[..., 2] = 60.0
    out = base.copy()
    out[invalid] = base[invalid] * (1.0 - alpha) + tint[invalid] * alpha
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), mode="RGB")


def gen_mapp_float(mapp, valid, range0, range1, imgsize, resize_map) -> np.ndarray:
    mapp_s = np.copy(mapp)
    mapp_s[valid == 0] = np.min(mapp_s[valid > 0])
    return resize_map(mapp_s, range0, range1, imgsize)


def gen_mapp_uint8(mapp, valid, range0, range1, imgsize, resize_map, vmax=None, vmin=None) -> np.ndarray:
    mapp_s = np.copy(mapp)
    mapp_s[valid == 0] = np.min(mapp_s[valid > 0])
    if vmax is None:
        vmax = np.nanmax(mapp_s)
    if vmin is None:
        vmin = np.nanmin(mapp_s)
    map_uint8 = (255 * (mapp_s.clip(vmin, vmax) - vmin) / (vmax - vmin)).clip(0, 255).astype(np.uint8)
    return 255 - resize_map(map_uint8, range0, range1, imgsize)


_INVALID_HEATMAP_RGB = np.array([120, 120, 120], dtype=np.uint8)


def heatmap_float_to_rgb(
    mapp_float: np.ndarray,
    valid_mask_full: np.ndarray | None = None,
) -> np.ndarray:
    """Jet colormap; vmin/vmax from valid pixels only, invalid regions stay neutral gray."""
    import matplotlib.cm as cm

    h, w = mapp_float.shape[:2]
    out = np.tile(_INVALID_HEATMAP_RGB, (h, w, 1))

    if valid_mask_full is not None:
        valid = (valid_mask_full >= 0.5) & np.isfinite(mapp_float)
    else:
        valid = np.isfinite(mapp_float)

    if not np.any(valid):
        return out

    scores = mapp_float[valid]
    vmin = float(np.min(scores))
    vmax = float(np.max(scores))
    span = max(vmax - vmin, 1e-8)
    norm = np.clip((mapp_float - vmin) / span, 0.0, 1.0)
    jet_rgb = (cm.jet(norm)[..., :3] * 255).astype(np.uint8)
    out[valid] = jet_rgb[valid]
    return out


def overlay_heatmap_jet(
    original_rgb: np.ndarray,
    mapp_float: np.ndarray,
    valid_mask_full: np.ndarray | None = None,
    alpha: float = 0.45,
) -> Image.Image:
    colored = heatmap_float_to_rgb(mapp_float, valid_mask_full)
    base = original_rgb.astype(np.float32)
    over = colored.astype(np.float32)
    if base.shape[:2] != over.shape[:2]:
        import cv2

        over = cv2.resize(over, (base.shape[1], base.shape[0]), interpolation=cv2.INTER_LINEAR)
        if valid_mask_full is not None and valid_mask_full.shape[:2] != base.shape[:2]:
            valid_mask_full = cv2.resize(
                valid_mask_full.astype(np.float32),
                (base.shape[1], base.shape[0]),
                interpolation=cv2.INTER_NEAREST,
            )

    if valid_mask_full is not None:
        valid = valid_mask_full >= 0.5
        blended = base.copy()
        blended[valid] = base[valid] * (1.0 - alpha) + over[valid] * alpha
    else:
        blended = base * (1.0 - alpha) + over * alpha

    return Image.fromarray(np.clip(blended, 0, 255).astype(np.uint8), mode="RGB")


def heatmap_jet_image(
    mapp_float: np.ndarray,
    valid_mask_full: np.ndarray | None = None,
) -> Image.Image:
    return Image.fromarray(heatmap_float_to_rgb(mapp_float, valid_mask_full), mode="RGB")
