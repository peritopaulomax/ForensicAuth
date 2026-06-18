"""Wavelets Noise Residue — Peritus INC port (Mahdian & Saic 2009)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import cv2
import numpy as np

from core.legacy.wavelet_noise_residue.dwt import dwt_x, scaling_coefficients

ProgressFn = Optional[Callable[[int, str], None]]

DEFAULT_PARAMS = {
    "order": 8,
    "blocksize": 3,
    "thr": 255,
    "post": True,
    "levels": 1,
}

VALID_ORDERS = (2, 4, 6, 8, 10)

DWT_COEFFICIENTS_FILENAME = "wnr_dwt_coefficients.npz"


@dataclass
class WaveletNoiseResidueParams:
    order: int = 8
    blocksize: int = 3
    thr: int = 255
    post: bool = True
    levels: int = 1
    region: tuple[int, int, int, int] | None = None

    @classmethod
    def from_dict(cls, d: dict | None) -> "WaveletNoiseResidueParams":
        d = d or {}
        region = d.get("region")
        if region is not None and isinstance(region, (list, tuple)) and len(region) == 4:
            region = tuple(int(v) for v in region)
        else:
            region = None
        slider = d.get("levels_slider")
        order = int(d.get("order", DEFAULT_PARAMS["order"]))
        if slider is not None:
            order = 2 * int(slider)
        return cls(
            order=order,
            blocksize=int(d.get("blocksize", DEFAULT_PARAMS["blocksize"])),
            thr=int(d.get("thr", DEFAULT_PARAMS["thr"])),
            post=bool(d.get("post", DEFAULT_PARAMS["post"])),
            levels=int(d.get("levels", DEFAULT_PARAMS["levels"])),
            region=region,
        )


def _report(on_progress: ProgressFn, pct: int, msg: str) -> None:
    if on_progress:
        on_progress(pct, msg)


def _block_median(values: np.ndarray, blocksize: int) -> float:
    """Median of absolute values — Peritus qsort on blocksize² samples."""
    flat = values.ravel()
    n = blocksize * blocksize
    if flat.size > n:
        flat = flat[:n]
    if blocksize % 2:
        return float(np.median(flat))
    mid = n // 2
    sorted_flat = np.sort(flat)
    return float(sorted_flat[mid - 1] / 2.0 + sorted_flat[mid] / 2.0)


def compute_dwt_coefficients(
    gray: np.ndarray,
    *,
    order: int = 8,
    levels: int = 1,
) -> np.ndarray:
    """Run DWT only — expensive step reused for live blocksize/threshold preview."""
    if order not in VALID_ORDERS:
        raise ValueError(f"order invalido: {order}")

    if gray.ndim == 3:
        gray = cv2.cvtColor(gray, cv2.COLOR_BGR2GRAY)

    img_height, img_width = gray.shape[:2]
    entrada = gray.astype(np.float64, copy=False).ravel(order="C").copy()
    h = scaling_coefficients(order)
    return dwt_x(entrada.reshape(img_height, img_width), h, levels)


def aggregate_hh_residue(
    saida: np.ndarray,
    img_height: int,
    img_width: int,
    blocksize: int,
) -> np.ndarray:
    """Block median on HH subband, upscale and min-max normalize (before thr post)."""
    out_w = int(math.floor(img_width / (2 * blocksize)))
    out_h = int(math.floor(img_height / (2 * blocksize)))
    hh_row0 = img_height // 2
    hh_col0 = img_width // 2

    hh = np.abs(saida[hh_row0:img_height, hh_col0:img_width].astype(np.float64, copy=False))
    row_ok = (np.arange(out_h) * blocksize + out_h + blocksize - 1) < img_height
    col_ok = (np.arange(out_w) * blocksize + out_w + blocksize - 1) < img_width
    valid = row_ok[:, None] & col_ok[None, :]

    hh_use = hh[: out_h * blocksize, : out_w * blocksize]
    blocks = (
        hh_use.reshape(out_h, blocksize, out_w, blocksize)
        .transpose(0, 2, 1, 3)
        .reshape(out_h, out_w, blocksize * blocksize)
    )
    n = blocksize * blocksize
    if blocksize % 2:
        meds = np.median(blocks, axis=2)
    else:
        sorted_blocks = np.sort(blocks, axis=2)
        mid = n // 2
        meds = sorted_blocks[:, :, mid - 1] / 2.0 + sorted_blocks[:, :, mid] / 2.0

    dest = np.where(valid, meds, 0.0).astype(np.float32)
    dest_up = cv2.resize(dest, (img_width, img_height), interpolation=cv2.INTER_CUBIC)
    return cv2.normalize(dest_up, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8UC1)


def aggregated_residue_cache_path(cache_dir: Path, blocksize: int) -> Path:
    return cache_dir / f"wnr_agg_bs{blocksize}.npy"


def get_or_compute_aggregated_residue(
    saida: np.ndarray,
    img_height: int,
    img_width: int,
    blocksize: int,
    cache_dir: Path | None,
) -> np.ndarray:
    """Return pre-threshold aggregated residue; cache per blocksize for live preview."""
    if cache_dir is not None:
        path = aggregated_residue_cache_path(cache_dir, blocksize)
        if path.is_file():
            cached = np.load(str(path))
            if cached.shape == (img_height, img_width):
                return cached
    dest = aggregate_hh_residue(saida, img_height, img_width, blocksize)
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        np.save(str(aggregated_residue_cache_path(cache_dir, blocksize)), dest)
    return dest


def apply_residue_post(dest_norm: np.ndarray, *, thr: int, post: bool) -> np.ndarray:
    """Peritus post-processing: scale by threshold and re-normalize."""
    if not post:
        return dest_norm
    thr_safe = max(1, int(thr))
    scaled = np.clip(dest_norm.astype(np.float32) * 255.0 / thr_safe, 0, 255).astype(np.uint8)
    return cv2.normalize(scaled, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8UC1)


def residue_gray_to_colored(dest_norm: np.ndarray) -> np.ndarray:
    return cv2.applyColorMap(dest_norm, cv2.COLORMAP_JET)


def render_residue_visuals(
    gray_full: np.ndarray,
    colored_roi: np.ndarray,
    region: tuple[int, int, int, int] | None,
) -> dict[str, np.ndarray]:
    """Compose full-frame colored map, heatmap and overlay."""
    if region is not None:
        x, y, w, h = region
        canvas = cv2.cvtColor(gray_full, cv2.COLOR_GRAY2BGR)
        canvas[y : y + h, x : x + w] = colored_roi
        colored_bgr = canvas
    else:
        colored_bgr = colored_roi

    heatmap = cv2.cvtColor(colored_bgr, cv2.COLOR_BGR2GRAY)
    original_bgr = cv2.cvtColor(gray_full, cv2.COLOR_GRAY2BGR)
    overlay = cv2.addWeighted(original_bgr, 0.55, colored_bgr, 0.45, 0)
    return {
        "colored_bgr": colored_bgr,
        "heatmap": heatmap,
        "overlay_bgr": overlay,
        "original_bgr": original_bgr,
    }


def reprocess_from_dwt_coefficients(
    saida: np.ndarray,
    gray_full: np.ndarray,
    *,
    blocksize: int,
    thr: int,
    post: bool,
    region: tuple[int, int, int, int] | None = None,
    aggregate_cache_dir: Path | None = None,
) -> dict[str, np.ndarray]:
    """Re-aggregate HH blocks and apply post-processing without re-running DWT."""
    if region is not None:
        x, y, w, h = region
        work = gray_full[y : y + h, x : x + w]
    else:
        work = gray_full

    work_h, work_w = work.shape[:2]
    dest_norm = get_or_compute_aggregated_residue(
        saida, work_h, work_w, blocksize, aggregate_cache_dir
    )
    dest_norm = apply_residue_post(dest_norm, thr=thr, post=post)
    colored_roi = residue_gray_to_colored(dest_norm)
    return render_residue_visuals(gray_full, colored_roi, region)


def save_dwt_coefficients_npz(
    path: Path,
    *,
    saida: np.ndarray,
    gray_full: np.ndarray,
    order: int,
    levels: int,
    region: tuple[int, int, int, int] | None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    region_arr = np.array(region, dtype=np.int32) if region is not None else np.array([], dtype=np.int32)
    np.savez_compressed(
        str(path),
        saida=saida.astype(np.float64),
        gray_full=gray_full.astype(np.uint8),
        order=np.int32(order),
        levels=np.int32(levels),
        region=region_arr,
    )


def load_dwt_coefficients_npz(path: Path) -> dict:
    with np.load(str(path), allow_pickle=False) as archive:
        region_raw = archive["region"]
        region = tuple(int(v) for v in region_raw.tolist()) if region_raw.size == 4 else None
        return {
            "saida": archive["saida"],
            "gray_full": archive["gray_full"],
            "order": int(archive["order"]),
            "levels": int(archive["levels"]),
            "region": region,
        }


def reprocess_wavelet_noise_residue_from_npz(
    npz_path: Path,
    *,
    blocksize: int,
    thr: int,
    post: bool,
    aggregate_cache_dir: Path | None = None,
) -> dict[str, np.ndarray]:
    cached = load_dwt_coefficients_npz(npz_path)
    cache_dir = aggregate_cache_dir if aggregate_cache_dir is not None else npz_path.parent
    return reprocess_from_dwt_coefficients(
        cached["saida"],
        cached["gray_full"],
        blocksize=blocksize,
        thr=thr,
        post=post,
        region=cached["region"],
        aggregate_cache_dir=cache_dir,
    )


def wavelets_noise_residue(
    gray: np.ndarray,
    *,
    order: int = 8,
    blocksize: int = 3,
    thr: int = 255,
    post: bool = True,
    levels: int = 1,
) -> np.ndarray:
    """
    Run Peritus WaveletsNoiseResidue on grayscale uint8/float image.

    Returns BGR colormap (JET) same size as input.
    """
    saida = compute_dwt_coefficients(gray, order=order, levels=levels)
    if gray.ndim == 3:
        gray = cv2.cvtColor(gray, cv2.COLOR_BGR2GRAY)
    img_height, img_width = gray.shape[:2]
    dest_norm = aggregate_hh_residue(saida, img_height, img_width, blocksize)
    dest_norm = apply_residue_post(dest_norm, thr=thr, post=post)
    return residue_gray_to_colored(dest_norm)


def run_wavelet_noise_residue(
    gray: np.ndarray,
    params: WaveletNoiseResidueParams | dict | None = None,
    on_progress: ProgressFn = None,
    *,
    dwt_coefficients_path: Path | None = None,
) -> dict:
    """Full pipeline with optional ROI and cached DWT coefficients for live preview."""
    p = params if isinstance(params, WaveletNoiseResidueParams) else WaveletNoiseResidueParams.from_dict(params)

    if gray.ndim == 3:
        gray = cv2.cvtColor(gray, cv2.COLOR_BGR2GRAY)

    _report(on_progress, 5, "Preparando imagem")
    gray_full = gray
    meta: dict = {"roi_applied": False}
    region = p.region

    if region is not None:
        x, y, w, h = region
        x = max(0, min(x, gray.shape[1] - 1))
        y = max(0, min(y, gray.shape[0] - 1))
        w = max(1, min(w, gray.shape[1] - x))
        h = max(1, min(h, gray.shape[0] - y))
        region = (x, y, w, h)
        meta["roi_applied"] = True
        meta["region"] = region

    _report(on_progress, 15, "Wavelets Noise Residue — DWT (Peritus)")
    if region is not None:
        x, y, w, h = region
        work = gray[y : y + h, x : x + w]
    else:
        work = gray

    saida = compute_dwt_coefficients(work, order=p.order, levels=p.levels)

    if dwt_coefficients_path is not None:
        save_dwt_coefficients_npz(
            dwt_coefficients_path,
            saida=saida,
            gray_full=gray_full,
            order=p.order,
            levels=p.levels,
            region=region,
        )

    _report(on_progress, 70, "Agregacao HH e pos-processamento")
    visuals = reprocess_from_dwt_coefficients(
        saida,
        gray_full,
        blocksize=p.blocksize,
        thr=p.thr,
        post=p.post,
        region=region,
        aggregate_cache_dir=dwt_coefficients_path.parent if dwt_coefficients_path else None,
    )

    _report(on_progress, 100, "Wavelets Noise Residue concluido")

    return {
        **visuals,
        "prep_meta": meta,
        "parameters": {
            "order": p.order,
            "blocksize": p.blocksize,
            "thr": p.thr,
            "post": p.post,
            "levels": p.levels,
        },
    }
