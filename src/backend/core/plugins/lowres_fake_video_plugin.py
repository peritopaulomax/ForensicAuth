"""Low-Resolution Fake Video Detection adapter (lukasHoel / TUM)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Tuple

from core.forensic_plugin import ForensicPlugin
from core.job_staging import job_artifact_dir
from core.legacy.lowres_fake_video.lfv_pipeline import run_lfv_analysis, write_lfv_report
from core.legacy.lowres_fake_video.lfv_runtime import lfv_runtime_status
from core.progress import pop_progress_callback, report_progress


class LowResFakeVideoPlugin(ForensicPlugin):
    @property
    def name(self) -> str:
        return "lowres_fake_video"

    @property
    def supported_types(self) -> list[str]:
        return ["video"]

    @classmethod
    def is_runtime_available(cls) -> Tuple[bool, str]:
        return lfv_runtime_status()

    def validate_parameters(self, parameters: Dict[str, Any]) -> Tuple[bool, str]:
        ok, reason = lfv_runtime_status()
        if not ok:
            return False, reason
        return True, ""

    def analyze(self, evidence_path: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        on_progress = pop_progress_callback(parameters)
        ok, reason = lfv_runtime_status()
        if not ok:
            return {"success": False, "error": reason, "adapter": "lfv", "status": "unavailable"}
        try:
            out_dir = job_artifact_dir(parameters, fallback_subdir="lfv_tmp")
            analysis = run_lfv_analysis(
                evidence_path,
                sample_every=int(parameters.get("sample_every", 5)),
                max_frames=int(parameters.get("max_frames", 80)),
                out_dir=out_dir,
                on_progress=on_progress,
            )
            json_path, txt_path = write_lfv_report(analysis, out_dir)
            result: Dict[str, Any] = {
                "success": True,
                "adapter": "lfv",
                "status": "completed",
                "video_decision": analysis.video_decision,
                "mean_score": analysis.mean_score,
                "max_score": analysis.max_score,
                "max_frame_idx": analysis.max_frame_idx,
                "inference_device": analysis.inference_device,
                "lfv_report_json_path": json_path,
                "lfv_summary_txt_path": txt_path,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            if analysis.scores_chart_path:
                result["lfv_scores_chart_path"] = analysis.scores_chart_path
            report_progress(on_progress, 100, "Concluido")
            return result
        except Exception as exc:
            return {"success": False, "error": str(exc), "adapter": "lfv"}
