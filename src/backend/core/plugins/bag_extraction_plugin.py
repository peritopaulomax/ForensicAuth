"""Extracao BAG (Block Artifact Grid) — mapa de desalinhamento de blocos JPEG 8x8."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

import cv2
import numpy as np
from scipy.ndimage import convolve, median_filter as medfilt2d

from app.config import get_settings
from core.forensic_plugin import ForensicPlugin
from core.job_staging import job_artifact_dir
from core.progress import pop_progress_callback, report_progress


def _block_value(blocks: np.ndarray) -> np.ndarray:
    """Block value metric for 8x8 JPEG blocks (sum of edge vs interior differences)."""
    block_data = blocks.reshape(blocks.shape[0], blocks.shape[1], 8, 8)
    max1 = np.max(np.sum(block_data[:, :, 1:7, 1:7], axis=3), axis=2)
    min1 = np.min(np.sum(block_data[:, :, 1:7, [0, 7]], axis=3), axis=2)
    max2 = np.max(np.sum(block_data[:, :, 1:7, 1:7], axis=2), axis=2)
    min2 = np.min(np.sum(block_data[:, :, [0, 7], 1:7], axis=2), axis=2)
    return max1 - min1 + max2 - min2


def _view_as_blocks(arr: np.ndarray, block_size: Tuple[int, int]) -> np.ndarray:
    bh, bw = block_size
    h, w = arr.shape
    return arr.reshape(h // bh, bh, w // bw, bw).transpose(0, 2, 1, 3)


class BagExtractionPlugin(ForensicPlugin):
    """Extract block artifact grid misalignment map from luminance channel."""

    @property
    def name(self) -> str:
        return "bag_extraction"

    @property
    def supported_types(self) -> list[str]:
        return ["imagem"]

    def validate_parameters(self, parameters: Dict[str, Any]) -> Tuple[bool, str]:
        diff_thresh = float(parameters.get("diff_thresh", 50))
        ac = int(parameters.get("ac", 33))
        if diff_thresh <= 0:
            return False, "diff_thresh deve ser positivo"
        if ac < 3:
            return False, "ac deve ser >= 3"
        return True, ""

    def analyze(self, evidence_path: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        on_progress = pop_progress_callback(parameters)
        try:
            report_progress(on_progress, 10, "Carregando imagem")
            im = cv2.imread(evidence_path)
            if im is None:
                return {"success": False, "error": "Falha ao carregar imagem", "adapter": "bag_extraction"}

            height, width = im.shape[:2]
            pad_height = (8 - (height % 8)) % 8
            pad_width = (8 - (width % 8)) % 8
            if pad_height > 0 or pad_width > 0:
                im = np.pad(im, ((0, pad_height), (0, pad_width), (0, 0)), mode="constant", constant_values=0)

            ycbcr = cv2.cvtColor(im, cv2.COLOR_BGR2YCrCb)
            y = ycbcr[:, :, 0].astype(float)

            diff_thresh = float(parameters.get("diff_thresh", 50))
            ac = int(parameters.get("ac", 33))

            report_progress(on_progress, 25, "Derivada vertical (grade)")
            im2_diff_y = -np.diff(np.vstack([y[0, :], y, y[-1, :]]), n=2, axis=0)
            im2_diff_y[np.abs(im2_diff_y) > diff_thresh] = 0
            padded = np.pad(im2_diff_y, ((0, 0), (round((ac - 1) / 2), round((ac - 1) / 2))), mode="symmetric")
            summed_h = convolve(np.abs(padded), np.ones((1, ac)), mode="constant", cval=0.0)
            summed_h = summed_h[:, round((ac - 1) / 2) : -round((ac - 1) / 2)]
            mid = medfilt2d(summed_h, size=(ac, 1))
            eh = summed_h - mid
            padded_horz = np.pad(eh, ((16, 16), (0, 0)), mode="symmetric")

            horz_mid = np.zeros((padded_horz.shape[0] - 32, padded_horz.shape[1], 5))
            horz_mid[:, :, 0] = padded_horz[0:-32, :]
            horz_mid[:, :, 1] = padded_horz[8:-24, :]
            horz_mid[:, :, 2] = padded_horz[16:-16, :]
            horz_mid[:, :, 3] = padded_horz[24:-8, :]
            horz_mid[:, :, 4] = padded_horz[32:, :]
            horz_mid = np.median(horz_mid, axis=2)

            report_progress(on_progress, 50, "Derivada horizontal (grade)")
            im2_diff_x = -np.diff(np.hstack([y[:, 0].reshape(-1, 1), y, y[:, -1].reshape(-1, 1)]), n=2, axis=1)
            im2_diff_x[np.abs(im2_diff_x) > diff_thresh] = 0
            padded = np.pad(im2_diff_x, ((round((ac - 1) / 2), round((ac - 1) / 2)), (0, 0)), mode="symmetric")
            summed_v = convolve(np.abs(padded), np.ones((ac, 1)), mode="constant", cval=0.0)
            summed_v = summed_v[round((ac - 1) / 2) : -round((ac - 1) / 2), :]
            mid = medfilt2d(summed_v, size=(1, ac))
            ev = summed_v - mid
            padded_vert = np.pad(ev, ((0, 0), (16, 16)), mode="symmetric")

            vert_mid = np.zeros((padded_vert.shape[0], padded_vert.shape[1] - 32, 5))
            vert_mid[:, :, 0] = padded_vert[:, 0:-32]
            vert_mid[:, :, 1] = padded_vert[:, 8:-24]
            vert_mid[:, :, 2] = padded_vert[:, 16:-16]
            vert_mid[:, :, 3] = padded_vert[:, 24:-8]
            vert_mid[:, :, 4] = padded_vert[:, 32:]
            vert_mid = np.median(vert_mid, axis=2)

            report_progress(on_progress, 70, "Agregando blocos 8x8")
            block_diff = horz_mid + vert_mid
            blocks = _view_as_blocks(block_diff, (8, 8))
            b = _block_value(blocks)
            bag_map = b.repeat(8, axis=0).repeat(8, axis=1)
            bag_map = bag_map[: height + pad_height, : width + pad_width]

            settings = get_settings()
            result_dir = job_artifact_dir(parameters, fallback_subdir="bag_tmp")
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

            report_progress(on_progress, 80, "Salvando mapa e overlay")
            original_path = result_dir / f"original_{stamp}.png"
            map_path = result_dir / f"bag_map_{stamp}.png"
            overlay_path = result_dir / f"overlay_{stamp}.png"

            cv2.imwrite(str(original_path), im[: height + pad_height, : width + pad_width])

            bmin, bmax = float(np.min(bag_map)), float(np.max(bag_map))
            span = bmax - bmin or 1.0
            map_u8 = ((bag_map - bmin) / span * 255).astype(np.uint8)
            map_color = cv2.applyColorMap(map_u8, cv2.COLORMAP_INFERNO)
            cv2.imwrite(str(map_path), map_color)

            overlay = im[: height + pad_height, : width + pad_width].copy()
            overlay = cv2.addWeighted(overlay, 0.55, map_color, 0.45, 0)
            cv2.imwrite(str(overlay_path), overlay)

            return {
                "success": True,
                "adapter": "bag_extraction",
                "status": "completed",
                "map_min": bmin,
                "map_max": bmax,
                "map_mean": float(np.mean(bag_map)),
                "parameters": {"diff_thresh": diff_thresh, "ac": ac},
                "original_crop_path": str(original_path),
                "bag_map_image_path": str(map_path),
                "overlay_image_path": str(overlay_path),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as exc:
            return {"success": False, "error": str(exc), "adapter": "bag_extraction"}
