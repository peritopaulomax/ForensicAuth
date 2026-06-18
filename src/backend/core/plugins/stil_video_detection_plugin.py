"""STIL adapter — deepfake video detection (ACM MM 2021)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

from core.forensic_plugin import ForensicPlugin
from core.job_staging import job_artifact_dir
from core.legacy.stil.stil_pipeline import run_stil_analysis, write_stil_report
from core.legacy.stil.stil_runtime import CLIP_SIZE, stil_runtime_status
from core.progress import pop_progress_callback, report_progress


class StilVideoDetectionPlugin(ForensicPlugin):
    @property
    def name(self) -> str:
        return "stil_video_detection"

    @property
    def supported_types(self) -> list[str]:
        return ["video"]

    @classmethod
    def is_runtime_available(cls) -> Tuple[bool, str]:
        return stil_runtime_status()

    def validate_parameters(self, parameters: Dict[str, Any]) -> Tuple[bool, str]:
        ok, reason = stil_runtime_status()
        if not ok:
            return False, reason
        sample_every = int(parameters.get("sample_every", 4))
        if sample_every < 1 or sample_every > 60:
            return False, "sample_every deve estar entre 1 e 60"
        max_frames = int(parameters.get("max_frames", 64))
        if max_frames < CLIP_SIZE or max_frames > 256:
            return False, "max_frames deve estar entre 8 e 256"
        return True, ""

    def analyze(self, evidence_path: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        on_progress = pop_progress_callback(parameters)
        ok, reason = stil_runtime_status()
        if not ok:
            return {"success": False, "error": reason, "adapter": "stil", "status": "unavailable"}
        try:
            out_dir = job_artifact_dir(parameters, fallback_subdir="stil_tmp")
            analysis = run_stil_analysis(
                evidence_path,
                sample_every=int(parameters.get("sample_every", 4)),
                max_frames=int(parameters.get("max_frames", 64)),
                out_dir=out_dir,
                on_progress=on_progress,
            )
            json_path, txt_path = write_stil_report(analysis, out_dir)
            result: Dict[str, Any] = {
                "success": True,
                "adapter": "stil",
                "status": "completed",
                "video_decision": analysis.video_decision,
                "mean_score": analysis.mean_score,
                "max_score": analysis.max_score,
                "max_start_frame": analysis.max_start_frame,
                "inference_device": analysis.inference_device,
                "stil_report_json_path": json_path,
                "stil_summary_txt_path": txt_path,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            if analysis.scores_chart_path:
                result["stil_scores_chart_path"] = analysis.scores_chart_path
            report_progress(on_progress, 100, "Concluido")
            return result
        except Exception as exc:
            return {"success": False, "error": str(exc), "adapter": "stil"}
