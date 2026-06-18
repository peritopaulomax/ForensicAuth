"""DistilDIRE adapter — deteccao leve de imagens sintetizadas por difusao."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

from core.forensic_plugin import ForensicPlugin
from core.job_staging import job_artifact_dir
from core.legacy.distildire.distildire_pipeline import (
    run_distildire_analysis,
    write_distildire_report,
)
from core.legacy.distildire.distildire_runtime import (
    CheckpointKind,
    distildire_runtime_status,
)
from core.progress import pop_progress_callback, report_progress


class DistilDirePlugin(ForensicPlugin):
    """DistilDIRE — reconstrucao DIRE em um passo (ResNet-50 + ADM 256)."""

    @property
    def name(self) -> str:
        return "distildire"

    @property
    def supported_types(self) -> list[str]:
        return ["imagem"]

    @classmethod
    def is_runtime_available(cls) -> Tuple[bool, str]:
        return distildire_runtime_status()

    def validate_parameters(self, parameters: Dict[str, Any]) -> Tuple[bool, str]:
        checkpoint = str(parameters.get("checkpoint", "imagenet")).lower()
        if checkpoint not in ("imagenet", "celebahq"):
            return False, "checkpoint deve ser 'imagenet' ou 'celebahq'"

        ok, reason = distildire_runtime_status(require_checkpoint=checkpoint)  # type: ignore[arg-type]
        if not ok:
            return False, reason

        threshold = float(parameters.get("threshold", 0.5))
        if threshold < 0.0 or threshold > 1.0:
            return False, "threshold deve estar entre 0 e 1"

        return True, ""

    def analyze(self, evidence_path: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        on_progress = pop_progress_callback(parameters)
        checkpoint: CheckpointKind = str(parameters.get("checkpoint", "imagenet")).lower()  # type: ignore[assignment]
        ok, reason = distildire_runtime_status(require_checkpoint=checkpoint)
        if not ok:
            return {"success": False, "error": reason, "adapter": "distildire", "status": "unavailable"}

        try:
            threshold = float(parameters.get("threshold", 0.5))
            generate_visuals = bool(parameters.get("generate_visuals", True))

            analysis = run_distildire_analysis(
                evidence_path,
                checkpoint=checkpoint,
                threshold=threshold,
                generate_visuals=generate_visuals,
                on_progress=on_progress,
            )

            stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            out_dir = job_artifact_dir(parameters, fallback_subdir="distildire_tmp")
            report_progress(on_progress, 90, "Salvando artefatos")

            def save_pil(img, filename: str) -> str | None:
                if img is None:
                    return None
                path = out_dir / f"{filename}_{stamp}.png"
                if hasattr(img, "mode") and img.mode not in ("RGB", "L"):
                    img = img.convert("RGB")
                img.save(path, format="PNG")
                return str(path)

            json_path, txt_path = write_distildire_report(analysis, out_dir)

            result: Dict[str, Any] = {
                "success": True,
                "adapter": "distildire",
                "status": "completed",
                "checkpoint": analysis.checkpoint,
                "df_probability": analysis.df_probability,
                "prediction": analysis.prediction,
                "threshold": analysis.threshold,
                "inference_device": analysis.inference_device,
                "gpu_fallback_reason": analysis.gpu_fallback_reason,
                "distildire_report_json_path": json_path,
                "distildire_summary_txt_path": txt_path,
                "input_image_path": save_pil(analysis.input_image, "input_image"),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            if analysis.eps_heatmap is not None:
                result["distildire_eps_heatmap_path"] = save_pil(
                    analysis.eps_heatmap, "distildire_eps_heatmap"
                )

            report_progress(on_progress, 100, "Concluido")
            return result

        except Exception as exc:
            return {"success": False, "error": str(exc), "adapter": "distildire"}
