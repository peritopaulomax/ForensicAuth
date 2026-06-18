"""SAFIRE adapter — forged region localization (AAAI 2025)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

from core.forensic_plugin import ForensicPlugin
from core.job_staging import job_artifact_dir
from core.legacy.safire.safire_pipeline import run_safire_analysis
from core.legacy.safire.safire_runtime import safire_runtime_status
from core.progress import pop_progress_callback, report_progress


class SafireAdapter(ForensicPlugin):
    """SAFIRE — localizacao binaria de falsificacao e particionamento multi-fonte."""

    @property
    def name(self) -> str:
        return "safire"

    @property
    def supported_types(self) -> list[str]:
        return ["imagem"]

    @classmethod
    def is_runtime_available(cls) -> Tuple[bool, str]:
        return safire_runtime_status()

    def validate_parameters(self, parameters: Dict[str, Any]) -> Tuple[bool, str]:
        ok, reason = safire_runtime_status()
        if not ok:
            return False, reason

        mode = str(parameters.get("mode", "binary"))
        if mode not in ("binary", "multi"):
            return False, "mode deve ser 'binary' ou 'multi'"

        cluster_type = str(parameters.get("cluster_type", "kmeans"))
        if cluster_type not in ("kmeans", "dbscan"):
            return False, "cluster_type deve ser 'kmeans' ou 'dbscan'"

        k = int(parameters.get("kmeans_cluster_num", 3))
        if k < 2 or k > 8:
            return False, "kmeans_cluster_num deve estar entre 2 e 8"

        pps = int(parameters.get("points_per_side", 16))
        if pps < 8 or pps > 32:
            return False, "points_per_side deve estar entre 8 e 32"

        return True, ""

    def analyze(self, evidence_path: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        on_progress = pop_progress_callback(parameters)
        ok, reason = safire_runtime_status()
        if not ok:
            return {"success": False, "error": reason, "adapter": "safire", "status": "unavailable"}

        try:
            mode = str(parameters.get("mode", "binary"))
            analysis = run_safire_analysis(
                evidence_path,
                mode=mode,
                cluster_type=str(parameters.get("cluster_type", "kmeans")),
                kmeans_cluster_num=int(parameters.get("kmeans_cluster_num", 3)),
                dbscan_eps=float(parameters.get("dbscan_eps", 0.2)),
                dbscan_min_samples=int(parameters.get("dbscan_min_samples", 1)),
                points_per_side=int(parameters.get("points_per_side", 16)),
                points_per_batch=int(parameters.get("points_per_batch", 256)),
                on_progress=on_progress,
            )

            stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            out_dir = job_artifact_dir(parameters, fallback_subdir="safire_tmp")

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
                "adapter": "safire",
                "status": "completed",
                "mode": analysis.mode,
                "cluster_type": analysis.cluster_type,
                "cluster_count": analysis.cluster_count,
                "mean_forgery_score": analysis.mean_forgery_score,
                "inference_device": analysis.inference_device,
                "points_per_side_effective": analysis.points_per_side_effective,
                "points_per_batch_effective": analysis.points_per_batch_effective,
                "gpu_fallback_reason": analysis.gpu_fallback_reason,
                "gpu_fallback_warning": analysis.gpu_fallback_warning,
                "original_size": list(analysis.original_size),
                "inference_size": list(analysis.inference_size),
                "input_image_path": save_pil(analysis.input_image, "input_image"),
                "heatmap_path": save_pil(analysis.heatmap_image, "safire_heatmap"),
                "overlay_image_path": save_pil(analysis.overlay_image, "safire_overlay"),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            if analysis.multi_segment_image is not None:
                result["multi_segment_image_path"] = save_pil(
                    analysis.multi_segment_image, "safire_multi_segment"
                )

            report_progress(on_progress, 100, "Concluido")
            return result

        except Exception as exc:
            return {"success": False, "error": str(exc), "adapter": "safire"}
