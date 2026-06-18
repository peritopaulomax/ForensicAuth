"""ZERO JPEG grid / forgery detection plugin (libzero.so_)."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

import cv2
import numpy as np

from app.config import get_settings
from core.forensic_plugin import ForensicPlugin
from core.job_staging import job_artifact_dir
from core.legacy.zero.libzero_loader import zero_runtime_status
from core.legacy.zero.zero_pipeline import run_zero_analysis
from core.progress import pop_progress_callback, report_progress


class ZeroGridPlugin(ForensicPlugin):
    """ZERO algorithm — block grid votes and forgery regions via libzero."""

    @property
    def name(self) -> str:
        return "zero_grid"

    @property
    def supported_types(self) -> list[str]:
        return ["imagem"]

    @classmethod
    def is_runtime_available(cls) -> Tuple[bool, str]:
        return zero_runtime_status()

    def validate_parameters(self, parameters: Dict[str, Any]) -> Tuple[bool, str]:
        ok, reason = zero_runtime_status()
        if not ok:
            return False, reason
        q = int(parameters.get("simulation_quality", 99))
        if not (1 <= q <= 100):
            return False, "simulation_quality deve estar entre 1 e 100"
        return True, ""

    def analyze(self, evidence_path: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        on_progress = pop_progress_callback(parameters)
        ok, reason = zero_runtime_status()
        if not ok:
            return {"success": False, "error": reason, "adapter": "zero_grid"}

        try:
            report_progress(on_progress, 2, "Carregando evidencia")
            image = cv2.imread(evidence_path)
            if image is None:
                return {"success": False, "error": "Falha ao carregar imagem", "adapter": "zero_grid"}

            include_simulation = bool(parameters.get("include_simulation", False))
            simulation_quality = int(parameters.get("simulation_quality", 99))

            analysis = run_zero_analysis(
                image,
                include_simulation=include_simulation,
                simulation_quality=simulation_quality,
                on_progress=on_progress,
            )

            settings = get_settings()
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            out_dir = job_artifact_dir(parameters, fallback_subdir="zero_grid_tmp")

            paths = {
                "original": out_dir / f"original_{stamp}.png",
                "votes": out_dir / f"votes_colored_{stamp}.png",
                "forgery": out_dir / f"forgery_{stamp}.png",
                "overlay": out_dir / f"overlay_{stamp}.png",
            }

            cv2.imwrite(str(paths["original"]), image)
            cv2.imwrite(str(paths["votes"]), cv2.cvtColor(analysis["colored_votes"], cv2.COLOR_RGB2BGR))

            forgery = analysis["forgery_mask"]
            forgery_u8 = np.clip(forgery, 0, 255).astype(np.uint8)
            forgery_heat = cv2.applyColorMap(forgery_u8, cv2.COLORMAP_HOT)
            cv2.imwrite(str(paths["forgery"]), forgery_heat)

            overlay = image.copy()
            mask_bool = forgery_u8 > 0
            overlay[mask_bool] = (
                overlay[mask_bool].astype(np.float32) * 0.45 + np.array([0, 0, 255], dtype=np.float32) * 0.55
            ).astype(np.uint8)
            cv2.imwrite(str(paths["overlay"]), overlay)

            result: Dict[str, Any] = {
                "success": True,
                "adapter": "zero_grid",
                "status": "completed",
                "main_grid": analysis["main_grid"],
                "main_grid_dx": analysis["main_grid_dx"],
                "main_grid_dy": analysis["main_grid_dy"],
                "main_grid_detected": analysis["main_grid_detected"],
                "main_grid_misaligned": analysis["main_grid_misaligned"],
                "lnfa_grids": analysis["lnfa_grids"],
                "significant_grids": analysis["significant_grids"],
                "forgery_found_pass1": analysis["forgery_found_pass1"],
                "forgery_found_pass2": analysis["forgery_found_pass2"],
                "forged_regions_pass1": analysis["forged_regions_pass1"],
                "forged_regions_pass2": analysis["forged_regions_pass2"],
                "include_simulation": include_simulation,
                "original_crop_path": str(paths["original"]),
                "votes_colored_image_path": str(paths["votes"]),
                "forgery_image_path": str(paths["forgery"]),
                "overlay_image_path": str(paths["overlay"]),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            if analysis.get("colored_votes_simulated") is not None:
                sim_path = out_dir / f"votes_sim_{stamp}.png"
                cv2.imwrite(
                    str(sim_path),
                    cv2.cvtColor(analysis["colored_votes_simulated"], cv2.COLOR_RGB2BGR),
                )
                result["votes_simulated_image_path"] = str(sim_path)

            report_progress(on_progress, 100, "Concluido")
            return result

        except Exception as exc:
            return {"success": False, "error": str(exc), "adapter": "zero_grid"}
