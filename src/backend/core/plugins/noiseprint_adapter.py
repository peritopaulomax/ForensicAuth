"""Noiseprint adapter — CNN camera model fingerprint."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

from core.forensic_plugin import ForensicPlugin
from core.job_staging import job_artifact_dir
from core.legacy.noiseprint.noiseprint_pipeline import run_noiseprint_analysis
from core.legacy.noiseprint.noiseprint_runtime import noiseprint_runtime_status
from core.progress import pop_progress_callback, report_progress


class NoiseprintAdapter(ForensicPlugin):
    """Noiseprint — impressao digital do modelo de camera (GRIP-UNINA)."""

    @property
    def name(self) -> str:
        return "noiseprint"

    @property
    def supported_types(self) -> list[str]:
        return ["imagem"]

    @classmethod
    def is_runtime_available(cls) -> Tuple[bool, str]:
        return noiseprint_runtime_status()

    def validate_parameters(self, parameters: Dict[str, Any]) -> Tuple[bool, str]:
        ok, reason = noiseprint_runtime_status()
        if not ok:
            return False, reason
        return True, ""

    def analyze(self, evidence_path: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        on_progress = pop_progress_callback(parameters)
        ok, reason = noiseprint_runtime_status()
        if not ok:
            return {"success": False, "error": reason, "adapter": "noiseprint", "status": "unavailable"}

        try:
            analysis = run_noiseprint_analysis(evidence_path, on_progress=on_progress)

            stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            out_dir = job_artifact_dir(parameters, fallback_subdir="noiseprint_tmp")

            def save_pil(img, filename: str) -> str | None:
                if img is None:
                    return None
                path = out_dir / f"{filename}_{stamp}.png"
                if hasattr(img, "mode") and img.mode not in ("RGB", "L"):
                    img = img.convert("RGB")
                img.save(path, format="PNG")
                return str(path)

            result: Dict[str, Any] = {
                "success": True,
                "adapter": "noiseprint",
                "status": "completed",
                "jpeg_quality_factor": analysis.jpeg_quality_factor,
                "mean_noiseprint": analysis.mean_noiseprint,
                "valid_pixel_fraction": analysis.valid_pixel_fraction,
                "inference_device": analysis.inference_device,
                "blind_status": analysis.blind_status,
                "original_size": list(analysis.original_size),
                "input_image_path": save_pil(analysis.input_image, "input_image"),
                "heatmap_path": save_pil(analysis.heatmap_image, "noiseprint_heatmap"),
                "overlay_image_path": save_pil(analysis.overlay_image, "noiseprint_overlay"),
                "noiseprint_image_path": save_pil(analysis.noiseprint_image, "noiseprint_map"),
                "valid_mask_image_path": save_pil(analysis.valid_mask_image, "noiseprint_valid_mask"),
                "valid_overlay_image_path": save_pil(analysis.valid_overlay_image, "noiseprint_valid_overlay"),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            report_progress(on_progress, 100, "Concluido")
            return result

        except Exception as exc:
            return {"success": False, "error": str(exc), "adapter": "noiseprint"}
