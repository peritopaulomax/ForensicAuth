"""VideoFACT adapter — deteccao de edicoes e deepfake em video (WACV 2024)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

from core.forensic_plugin import ForensicPlugin
from core.job_staging import job_artifact_dir
from core.legacy.videofact.videofact_pipeline import (
    run_videofact_analysis,
    write_videofact_report,
)
from core.legacy.videofact.videofact_runtime import videofact_runtime_status
from core.progress import pop_progress_callback, report_progress


class VideoFactPlugin(ForensicPlugin):
    """VideoFACT — atencao, contexto de cena e tracos forenses em video."""

    @property
    def name(self) -> str:
        return "videofact"

    @property
    def supported_types(self) -> list[str]:
        return ["video"]

    @classmethod
    def is_runtime_available(cls) -> Tuple[bool, str]:
        return videofact_runtime_status()

    def validate_parameters(self, parameters: Dict[str, Any]) -> Tuple[bool, str]:
        ok, reason = videofact_runtime_status()
        if not ok:
            return False, reason

        mode = str(parameters.get("mode", "both")).lower()
        if mode not in ("xfer", "df", "both"):
            return False, "mode deve ser 'xfer', 'df' ou 'both'"

        max_samples = int(parameters.get("max_num_samples", 100))
        if max_samples < 1 or max_samples > 500:
            return False, "max_num_samples deve estar entre 1 e 500"

        sample_every = int(parameters.get("sample_every", 5))
        if sample_every < 1 or sample_every > 120:
            return False, "sample_every deve estar entre 1 e 120"

        return True, ""

    def analyze(self, evidence_path: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        on_progress = pop_progress_callback(parameters)
        ok, reason = videofact_runtime_status()
        if not ok:
            return {"success": False, "error": reason, "adapter": "videofact", "status": "unavailable"}

        try:
            out_dir = job_artifact_dir(parameters, fallback_subdir="videofact_tmp")
            mode = str(parameters.get("mode", "both")).lower()
            require = ("xfer", "df") if mode == "both" else (mode,)
            ok_modes, reason_modes = videofact_runtime_status(require_modes=require)
            if not ok_modes:
                return {"success": False, "error": reason_modes, "adapter": "videofact"}

            analysis = run_videofact_analysis(
                evidence_path,
                mode=mode,
                shuffle=bool(parameters.get("shuffle", False)),
                max_num_samples=int(parameters.get("max_num_samples", 100)),
                sample_every=int(parameters.get("sample_every", 5)),
                batch_size_xfer=int(parameters.get("batch_size_xfer", 1)),
                batch_size_df=int(parameters.get("batch_size_df", 2)),
                num_workers=int(parameters.get("num_workers", 0)),
                out_dir=out_dir,
                on_progress=on_progress,
            )

            json_path, txt_path = write_videofact_report(analysis, out_dir)

            result: Dict[str, Any] = {
                "success": True,
                "adapter": "videofact",
                "status": "completed",
                "mode": mode,
                "total_frames_sampled": analysis.total_frames_sampled,
                "sample_every": analysis.sample_every,
                "inference_device": analysis.inference_device,
                "videofact_report_json_path": json_path,
                "videofact_summary_txt_path": txt_path,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            for m in analysis.modes:
                prefix = m.mode
                result[f"videofact_{prefix}_decision"] = m.video_decision
                result[f"videofact_{prefix}_mean_score"] = m.mean_score
                result[f"videofact_{prefix}_max_score"] = m.max_score
                result[f"videofact_{prefix}_max_frame"] = m.max_frame_idx
                if m.scores_chart_path:
                    result[f"videofact_{prefix}_scores_chart_path"] = m.scores_chart_path
                heatmap_dir = Path(m.frame_results[0].heatmap_path).parent if m.frame_results else None
                if heatmap_dir and heatmap_dir.is_dir():
                    result[f"videofact_{prefix}_heatmaps_dir"] = str(heatmap_dir)

            result["extract_bundle_dir"] = str(out_dir)
            report_progress(on_progress, 100, "Concluido")
            return result

        except Exception as exc:
            return {"success": False, "error": str(exc), "adapter": "videofact"}
