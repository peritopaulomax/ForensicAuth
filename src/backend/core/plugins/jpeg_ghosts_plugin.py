"""Deteccao de JPEG Ghosts — Farid (IEEE TIFS 2009)."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

import cv2
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from app.config import get_settings
from core.forensic_plugin import ForensicPlugin
from core.job_staging import job_artifact_dir
from core.legacy.jpeg_ghosts import run_jpeg_ghosts_analysis
from core.progress import pop_progress_callback, report_progress


def _ghost_to_u8(ghost: np.ndarray) -> np.ndarray:
    u8 = (np.clip(ghost, 0.0, 1.0) * 255).astype(np.uint8)
    return u8


def _metric_to_heatmap(metric: np.ndarray, vmax: float) -> np.ndarray:
    if vmax <= 0:
        vmax = float(np.max(metric)) or 1.0
    norm = np.clip(metric / vmax, 0.0, 1.0)
    u8 = (norm * 255).astype(np.uint8)
    return cv2.applyColorMap(u8, cv2.COLORMAP_HOT)


def _build_shift_grid(per_shift: List[Dict[str, Any]], peak_metric: float) -> np.ndarray:
    """Mosaico 8x8 dos melhores mapas fantasma por deslocamento."""
    tiles = []
    for entry in sorted(per_shift, key=lambda e: (e["dy"], e["dx"])):
        ghost = entry["ghost_map"]
        tiles.append(_ghost_to_u8(ghost))

    if not tiles:
        return np.zeros((64, 64), dtype=np.uint8)

    tile_h = max(t.shape[0] for t in tiles)
    tile_w = max(t.shape[1] for t in tiles)
    thumb_h = max(32, tile_h // 4)
    thumb_w = max(32, tile_w // 4)

    grid = np.zeros((8 * thumb_h, 8 * thumb_w), dtype=np.uint8)
    for idx, thumb in enumerate(tiles[:64]):
        row, col = divmod(idx, 8)
        resized = cv2.resize(thumb, (thumb_w, thumb_h), interpolation=cv2.INTER_AREA)
        y0, x0 = row * thumb_h, col * thumb_w
        grid[y0 : y0 + thumb_h, x0 : x0 + thumb_w] = resized

    return grid


def _save_quality_montage(
    qualities: List[int],
    ghost_maps: Dict[int, np.ndarray],
    metric_peaks: Dict[int, float],
    path: Path,
    cols: int = 3,
) -> None:
    n = len(qualities)
    if n == 0:
        return
    rows = int(np.ceil(n / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(4 * cols, 3.5 * rows))
    if rows == 1 and cols == 1:
        axes = np.array([[axes]])
    elif rows == 1:
        axes = axes.reshape(1, -1)
    elif cols == 1:
        axes = axes.reshape(-1, 1)

    for i, q in enumerate(qualities):
        r, c = divmod(i, cols)
        ax = axes[r, c]
        ax.imshow(ghost_maps[q], cmap="gray", vmin=0, vmax=1)
        peak = metric_peaks.get(q, 0.0)
        ax.set_title(f"Q={q} · pico métrica={peak:.3f}")
        ax.axis("off")

    for j in range(n, rows * cols):
        r, c = divmod(j, cols)
        axes[r, c].axis("off")

    fig.suptitle("Mapas fantasma por qualidade JPEG (melhor deslocamento)", fontsize=12)
    plt.tight_layout()
    fig.savefig(path, dpi=120, bbox_inches="tight")
    plt.close(fig)


class JPEGGhostsPlugin(ForensicPlugin):
    """JPEG Ghosts via recompression difference maps and grid-shift search."""

    @property
    def name(self) -> str:
        return "jpeg_ghosts"

    @property
    def supported_types(self) -> list[str]:
        return ["imagem"]

    def validate_parameters(self, parameters: Dict[str, Any]) -> Tuple[bool, str]:
        qmin = int(parameters.get("qmin", 50))
        qmax = int(parameters.get("qmax", 100))
        step = int(parameters.get("step", 10))
        if not (1 <= qmin < qmax <= 100):
            return False, "qmin e qmax devem estar entre 1 e 100, com qmin < qmax"
        if step < 1:
            return False, "step deve ser >= 1"
        block_size = int(parameters.get("block_size", 16))
        if block_size < 4:
            return False, "block_size deve ser >= 4"
        neighborhood_k = int(parameters.get("neighborhood_k", 3))
        if neighborhood_k < 1 or neighborhood_k % 2 == 0:
            return False, "neighborhood_k deve ser inteiro ímpar >= 1"
        return True, ""

    def analyze(self, evidence_path: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        on_progress = pop_progress_callback(parameters)
        try:
            image = cv2.imread(evidence_path)
            if image is None:
                return {"success": False, "error": "Falha ao carregar imagem", "adapter": "jpeg_ghosts"}

            qmin = int(parameters.get("qmin", 50))
            qmax = int(parameters.get("qmax", 100))
            step = int(parameters.get("step", 10))
            block_size = int(parameters.get("block_size", 16))
            neighborhood_k = int(parameters.get("neighborhood_k", 3))
            shift_search = bool(parameters.get("shift_search", True))
            settings = get_settings()
            n_jobs = settings.JPEG_GHOSTS_N_JOBS

            report_progress(on_progress, 2, "Carregando imagem")

            analysis = run_jpeg_ghosts_analysis(
                image,
                qmin=qmin,
                qmax=qmax,
                step=step,
                block_size=block_size,
                neighborhood_k=neighborhood_k,
                shift_search=shift_search,
                n_jobs=n_jobs,
                on_progress=on_progress,
            )

            settings = get_settings()
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            out_dir = job_artifact_dir(parameters, fallback_subdir="jpeg_ghosts_tmp")

            peak = float(analysis["peak_metric"])
            ghost_u8 = _ghost_to_u8(analysis["ghost_map"])
            metric_heat = _metric_to_heatmap(analysis["metric_map"], peak)

            paths = {
                "original": out_dir / f"original_{stamp}.png",
                "ghost": out_dir / f"ghost_map_{stamp}.png",
                "metric": out_dir / f"metric_map_{stamp}.png",
                "shift_grid": out_dir / f"shift_grid_{stamp}.png",
                "montage": out_dir / f"quality_montage_{stamp}.png",
            }

            cv2.imwrite(str(paths["original"]), image)
            cv2.imwrite(str(paths["ghost"]), ghost_u8)
            cv2.imwrite(str(paths["metric"]), metric_heat)

            if shift_search and len(analysis["per_shift"]) > 1:
                grid = _build_shift_grid(analysis["per_shift"], peak)
                cv2.imwrite(str(paths["shift_grid"]), grid)

            qualities: List[int] = analysis["qualities"]
            ghost_maps: Dict[int, np.ndarray] = analysis["ghost_maps_by_quality"]
            _save_quality_montage(
                qualities,
                ghost_maps,
                analysis["metric_peaks_by_quality"],
                paths["montage"],
            )

            quality_artifacts = {}
            for q in qualities:
                q_path = out_dir / f"ghost_q{q}_{stamp}.png"
                cv2.imwrite(str(q_path), _ghost_to_u8(ghost_maps[q]))
                quality_artifacts[str(q)] = str(q_path)

            report_progress(on_progress, 100, "Concluido")

            return {
                "success": True,
                "adapter": "jpeg_ghosts",
                "status": "completed",
                "best_dx": analysis["best_dx"],
                "best_dy": analysis["best_dy"],
                "best_quality": analysis["best_quality"],
                "peak_metric": peak,
                "shift_search": shift_search,
                "metric_peaks_by_quality": analysis["metric_peaks_by_quality"],
                "qualities": qualities,
                "quality_ghost_paths": quality_artifacts,
                "original_crop_path": str(paths["original"]),
                "ghost_map_image_path": str(paths["ghost"]),
                "metric_map_image_path": str(paths["metric"]),
                "shift_grid_image_path": str(paths["shift_grid"]) if paths["shift_grid"].exists() else None,
                "quality_montage_image_path": str(paths["montage"]),
                "parameters": analysis["parameters"],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as exc:
            return {"success": False, "error": str(exc), "adapter": "jpeg_ghosts"}
