"""Deteccao JPEG Ghosts — Farid (IEEE TIFS 2009)."""

from __future__ import annotations

import gc
from typing import Any, Callable, Dict, List, Optional, Tuple

import cv2
import numpy as np

ProgressFn = Optional[Callable[[int, str], None]]


def process_single_quality(image: np.ndarray, quality: int, block_size: int) -> np.ndarray:
    """Recompress at Q, block-average squared diff, normalize to [0, 1]."""
    original_float = image.astype(np.float32)
    kernel = np.ones((block_size, block_size), np.float32) / (block_size * block_size)

    encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)]
    _, encoded_img = cv2.imencode(".jpg", image, encode_param)
    compressed_img = cv2.imdecode(encoded_img, cv2.IMREAD_COLOR).astype(np.float32)
    del encoded_img
    gc.collect()

    diff = (original_float - compressed_img) ** 2
    del original_float, compressed_img
    gc.collect()

    convolved = np.zeros_like(diff)
    for channel in range(3):
        convolved[:, :, channel] = cv2.filter2D(diff[:, :, channel], -1, kernel)
    del diff
    gc.collect()

    averaged = np.mean(convolved, axis=2)
    del convolved

    vmin = float(np.min(averaged))
    vmax = float(np.max(averaged))
    span = vmax - vmin
    if span < 1e-12:
        normalized = np.zeros_like(averaged)
    else:
        normalized = (averaged - vmin) / span

    del averaged
    gc.collect()
    return normalized


def process_image(
    image: np.ndarray,
    qmin: int,
    qmax: int,
    step: int,
    block_size: int,
    n_jobs: int = 1,
) -> Tuple[List[int], List[np.ndarray]]:
    """Return (qualities, normalized ghost maps) for each quality in range."""
    qualities = list(range(int(qmin), int(qmax) + 1, int(step)))
    if not qualities:
        return [], []

    if n_jobs != 1:
        try:
            from joblib import Parallel, delayed

            images = Parallel(n_jobs=n_jobs, backend="loky")(
                delayed(process_single_quality)(image, q, block_size) for q in qualities
            )
            return qualities, images
        except Exception:
            pass

    images = [process_single_quality(image, q, block_size) for q in qualities]
    return qualities, images


def compute_metric(image: np.ndarray, neighborhood_k: int) -> np.ndarray:
    """Metrica local/global de razao de media entre mapas fantasma."""
    height, width = image.shape
    metrics = np.zeros_like(image, dtype=np.float32)
    integral_image = cv2.integral(image, sdepth=cv2.CV_32F)
    global_mean = float(np.mean(image))

    i_indices = np.arange(height)
    j_indices = np.arange(width)
    half = neighborhood_k // 2
    i_min = np.maximum(i_indices[:, None] - half, 0)
    i_max = np.minimum(i_indices[:, None] + half, height - 1)
    j_min = np.maximum(j_indices[None, :] - half, 0)
    j_max = np.minimum(j_indices[None, :] + half, width - 1)

    neighborhood_sum = (
        integral_image[i_max + 1, j_max + 1]
        - integral_image[i_max + 1, j_min]
        - integral_image[i_min, j_max + 1]
        + integral_image[i_min, j_min]
    )

    neighborhood_area = (i_max - i_min + 1) * (j_max - j_min + 1)
    mean_neighborhood = neighborhood_sum / neighborhood_area

    if global_mean != 0:
        total_pixels = height * width
        mean_non_neighborhood = (global_mean * total_pixels - neighborhood_sum) / (
            total_pixels - neighborhood_area + 1e-12
        )
        metrics = mean_neighborhood / (mean_non_neighborhood + 1e-12)
    else:
        metrics.fill(0.0)

    return metrics


def generate_shifted_images(image: np.ndarray) -> List[Tuple[np.ndarray, int, int]]:
    """64 JPEG grid alignments (dx, dy in 0..7)."""
    height, width = image.shape[:2]
    shifted: List[Tuple[np.ndarray, int, int]] = []
    for dx in range(8):
        for dy in range(8):
            shifted.append((image[dy:height, dx:width].copy(), dx, dy))
    return shifted


def _pick_best_quality(
    qualities: List[int],
    processed_images: List[np.ndarray],
    metrics_results: List[np.ndarray],
) -> Tuple[int, float, np.ndarray, np.ndarray]:
    best_q = qualities[0]
    best_peak = -np.inf
    best_ghost = processed_images[0]
    best_metric = metrics_results[0]

    for q, proc, met in zip(qualities, processed_images, metrics_results):
        peak = float(np.max(met))
        if peak > best_peak:
            best_peak = peak
            best_q = q
            best_ghost = proc
            best_metric = met

    return best_q, best_peak, best_ghost, best_metric


def run_jpeg_ghosts_analysis(
    image_bgr: np.ndarray,
    qmin: int = 50,
    qmax: int = 100,
    step: int = 10,
    block_size: int = 16,
    neighborhood_k: int = 3,
    shift_search: bool = True,
    n_jobs: int = 2,
    on_progress: ProgressFn = None,
) -> Dict[str, Any]:
    """
    Pipeline completo de deteccao de fantasmas JPEG.

    Returns dict with best shift, quality, maps, per-shift summaries, and
    all ghost maps at the winning shift (for quality slider in UI).
    """
    if image_bgr is None or image_bgr.size == 0:
        raise ValueError("Imagem invalida")

    def prog(pct: int, msg: str) -> None:
        if on_progress:
            on_progress(pct, msg)

    prog(5, "Preparando analise JPEG Ghosts")

    shifts = [(image_bgr, -1, -1)] if not shift_search else generate_shifted_images(image_bgr)
    n_shifts = len(shifts)

    per_shift: List[Dict[str, Any]] = []
    global_peak = -np.inf
    global_best: Optional[Dict[str, Any]] = None

    for s_idx, (shifted_img, dx, dy) in enumerate(shifts):
        base_pct = 10 + int(80 * s_idx / max(n_shifts, 1))
        label = f"deslocamento ({dx},{dy})" if shift_search else "sem busca de grade"
        prog(base_pct, f"Processando {label} ({s_idx + 1}/{n_shifts})")

        qualities, processed_images = process_image(
            shifted_img, qmin, qmax, step, block_size, n_jobs=n_jobs
        )
        if not qualities:
            continue

        metrics_results = [compute_metric(img, neighborhood_k) for img in processed_images]

        best_q, shift_peak, shift_ghost, shift_metric = _pick_best_quality(
            qualities, processed_images, metrics_results
        )

        per_shift.append(
            {
                "dx": dx,
                "dy": dy,
                "best_quality": best_q,
                "peak_metric": shift_peak,
                "ghost_map": shift_ghost,
            }
        )

        if shift_peak > global_peak:
            global_peak = shift_peak
            global_best = {
                "dx": dx,
                "dy": dy,
                "best_quality": best_q,
                "peak_metric": shift_peak,
                "ghost_map": shift_ghost,
                "metric_map": shift_metric,
                "qualities": qualities,
                "ghost_maps_by_quality": {int(q): proc for q, proc in zip(qualities, processed_images)},
                "metrics_by_quality": {int(q): met for q, met in zip(qualities, metrics_results)},
                "metric_peaks_by_quality": {
                    int(q): float(np.max(met)) for q, met in zip(qualities, metrics_results)
                },
            }

        del processed_images, metrics_results
        gc.collect()

    if global_best is None:
        raise RuntimeError("Nenhum resultado gerado")

    prog(95, "Finalizando")

    return {
        "best_dx": global_best["dx"],
        "best_dy": global_best["dy"],
        "best_quality": global_best["best_quality"],
        "peak_metric": global_best["peak_metric"],
        "ghost_map": global_best["ghost_map"],
        "metric_map": global_best["metric_map"],
        "qualities": global_best["qualities"],
        "ghost_maps_by_quality": global_best["ghost_maps_by_quality"],
        "metrics_by_quality": global_best["metrics_by_quality"],
        "metric_peaks_by_quality": global_best["metric_peaks_by_quality"],
        "per_shift": per_shift,
        "shift_search": shift_search,
        "parameters": {
            "qmin": qmin,
            "qmax": qmax,
            "step": step,
            "block_size": block_size,
            "neighborhood_k": neighborhood_k,
            "shift_search": shift_search,
            "n_jobs": n_jobs,
        },
    }
