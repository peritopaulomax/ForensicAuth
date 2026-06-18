"""IMDL-BenCo hub adapter — NeurIPS'24 benchmark for IMDL."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

from core.forensic_plugin import ForensicPlugin
from core.job_staging import job_artifact_dir
from core.legacy.imdlbenco.imdlbenco_catalog import get_method
from core.legacy.imdlbenco.imdlbenco_pipeline import run_imdlbenco_analysis
from core.legacy.imdlbenco.imdlbenco_runtime import (
    MESORCH_VARIANTS,
    imdlbenco_runtime_status,
    method_runtime_status,
    resolve_mesorch_checkpoint,
)
from core.progress import pop_progress_callback, report_progress

VALID_METHODS = {
    "trufor",
    "cat_net",
    "objectformer",
    "mesorch",
    "sparse_vit",
    "dinov3_iml",
    "co_transformers",
    "nfa_vit",
    "miml_apscnet",
    "forensic_hub",
    "opensdi",
}


class ImdlBencoAdapter(ForensicPlugin):
    """IMDL-BenCo — hub de localizacao de manipulacao (10 metodos)."""

    @property
    def name(self) -> str:
        return "imdlbenco"

    @property
    def supported_types(self) -> list[str]:
        return ["imagem"]

    @classmethod
    def is_runtime_available(cls) -> Tuple[bool, str]:
        return imdlbenco_runtime_status()

    def validate_parameters(self, parameters: Dict[str, Any]) -> Tuple[bool, str]:
        method = str(parameters.get("method", "")).strip()
        if method not in VALID_METHODS:
            return False, f"method deve ser um de: {', '.join(sorted(VALID_METHODS))}"

        status, reason = method_runtime_status(method)
        if status != "ready":
            return False, reason or f"Metodo {method} indisponivel"

        if method == "mesorch":
            variant = str(parameters.get("mesorch_variant", "standard")).strip()
            if variant not in MESORCH_VARIANTS:
                return False, "mesorch_variant deve ser 'standard' ou 'mesorch_p'"
            if resolve_mesorch_checkpoint(variant) is None:
                fname = MESORCH_VARIANTS[variant]
                return False, f"Pesos Mesorch ausentes: {fname}"

        threshold = float(parameters.get("threshold", 0.85))
        if threshold < 0.0 or threshold > 1.0:
            return False, "threshold deve estar entre 0.0 e 1.0"

        return True, ""

    def analyze(self, evidence_path: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        on_progress = pop_progress_callback(parameters)
        method = str(parameters.get("method", "")).strip()
        ok, reason = self.validate_parameters(parameters)
        if not ok:
            return {
                "success": False,
                "error": reason,
                "adapter": "imdlbenco",
                "status": "unavailable",
                "method": method,
            }

        spec = get_method(method)
        try:
            threshold = float(parameters.get("threshold", 0.85))
            mesorch_variant = str(parameters.get("mesorch_variant", "standard")).strip()
            analysis = run_imdlbenco_analysis(
                evidence_path,
                method=method,
                threshold=threshold,
                mesorch_variant=mesorch_variant,
                on_progress=on_progress,
            )

            stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            out_dir = job_artifact_dir(parameters, fallback_subdir="imdlbenco_tmp")

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
                "adapter": "imdlbenco",
                "status": "completed",
                "method": method,
                "method_name": spec.name if spec else method,
                "method_venue": spec.venue if spec else "",
                "threshold": threshold,
                "mesorch_variant": mesorch_variant if method == "mesorch" else None,
                "mean_manipulation_score": analysis.mean_score,
                "integrity_score": analysis.integrity_score,
                "inference_device": analysis.inference_device,
                "gpu_fallback_reason": analysis.gpu_fallback_reason,
                "gpu_fallback_warning": analysis.gpu_fallback_warning,
                "original_size": list(analysis.original_size),
                "inference_window_note": analysis.inference_window_note,
                "input_image_path": save_pil(analysis.input_image, "input_image"),
                "heatmap_path": save_pil(analysis.heatmap_image, "imdlbenco_heatmap"),
                "score_map_path": save_pil(analysis.score_map_image, "imdlbenco_score_map"),
                "overlay_image_path": save_pil(analysis.overlay_image, "imdlbenco_overlay"),
                "mask_image_path": save_pil(analysis.mask_image, "imdlbenco_mask"),
                "confidence_image_path": save_pil(analysis.confidence_image, "imdlbenco_confidence"),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            report_progress(on_progress, 100, "Concluido")
            return result

        except Exception as exc:
            return {"success": False, "error": str(exc), "adapter": "imdlbenco", "method": method}
