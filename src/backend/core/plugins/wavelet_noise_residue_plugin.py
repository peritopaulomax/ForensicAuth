"""Wavelets Noise Residue adapter — Peritus legacy (Mahdian & Saic 2009)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

import cv2
import numpy as np

from core.forensic_plugin import ForensicPlugin
from core.job_staging import job_artifact_dir
from core.legacy.wavelet_noise_residue import (
    DWT_COEFFICIENTS_FILENAME,
    WaveletNoiseResidueParams,
    run_wavelet_noise_residue,
)
from core.progress import pop_progress_callback, report_progress


class WaveletNoiseResiduePlugin(ForensicPlugin):
    """Extract wavelet noise residue to expose tampering inconsistencies."""

    @property
    def name(self) -> str:
        return "wavelet_noise_residue"

    @property
    def supported_types(self) -> list[str]:
        return ["imagem"]

    def validate_parameters(self, parameters: Dict[str, Any]) -> Tuple[bool, str]:
        order = int(parameters.get("order", 8))
        if parameters.get("levels_slider") is not None:
            order = 2 * int(parameters["levels_slider"])
        if order not in (2, 4, 6, 8, 10):
            return False, "order (Daubechies) deve ser 2, 4, 6, 8 ou 10"

        blocksize = int(parameters.get("blocksize", 3))
        if not (3 <= blocksize <= 80):
            return False, "blocksize deve estar entre 3 e 80"

        thr = int(parameters.get("thr", 255))
        if not (0 <= thr <= 255):
            return False, "thr deve estar entre 0 e 255"

        region = parameters.get("region")
        if region is not None:
            if not isinstance(region, (list, tuple)) or len(region) != 4:
                return False, "region deve ser [x, y, w, h]"
        return True, ""

    def analyze(self, evidence_path: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        on_progress = pop_progress_callback(parameters)
        try:
            report_progress(on_progress, 5, "Carregando imagem")
            im_bgr = cv2.imread(evidence_path)
            if im_bgr is None:
                return {
                    "success": False,
                    "error": "Falha ao carregar imagem",
                    "adapter": "wavelet_noise_residue",
                }

            params = WaveletNoiseResidueParams.from_dict(parameters)
            gray = cv2.cvtColor(im_bgr, cv2.COLOR_BGR2GRAY)

            stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            out_dir = job_artifact_dir(parameters, fallback_subdir="wavelet_noise_residue_tmp")
            npz_path = out_dir / DWT_COEFFICIENTS_FILENAME

            # Wavelet (DWT) only on submit; blocksize/thr/post use defaults for first render.
            wavelet_params = WaveletNoiseResidueParams(
                order=params.order,
                blocksize=3,
                thr=255,
                post=True,
                levels=params.levels,
                region=params.region,
            )

            result = run_wavelet_noise_residue(
                gray,
                wavelet_params,
                on_progress=lambda pct, msg: report_progress(on_progress, pct, msg),
                dwt_coefficients_path=npz_path,
            )

            paths = {
                "original": out_dir / f"original_{stamp}.png",
                "heatmap": out_dir / f"heatmap_{stamp}.png",
                "colored": out_dir / f"colored_{stamp}.png",
                "overlay": out_dir / f"overlay_{stamp}.png",
            }

            cv2.imwrite(str(paths["original"]), im_bgr)
            cv2.imwrite(str(paths["heatmap"]), result["heatmap"])
            cv2.imwrite(str(paths["colored"]), result["colored_bgr"])
            cv2.imwrite(str(paths["overlay"]), result["overlay_bgr"])

            report_progress(on_progress, 100, "Wavelets Noise Residue concluido")

            return {
                "success": True,
                "adapter": "wavelet_noise_residue",
                "status": "completed",
                "prep_meta": result.get("prep_meta", {}),
                "parameters": result["parameters"],
                "original_crop_path": str(paths["original"]),
                "heatmap_path": str(paths["heatmap"]),
                "colored_overlay_image_path": str(paths["colored"]),
                "overlay_image_path": str(paths["overlay"]),
                "dwt_coefficients_path": str(npz_path),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as exc:
            return {"success": False, "error": str(exc), "adapter": "wavelet_noise_residue"}
