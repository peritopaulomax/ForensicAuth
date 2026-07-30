"""TruVIL plugin — video inpainting localization (IEEE TDSC 2025)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Tuple

from core.forensic_plugin import ForensicPlugin
from core.job_staging import job_artifact_dir
from core.progress import pop_progress_callback, report_progress
from forensics.truvil.truvil_pipeline import run_truvil_analysis, write_truvil_report
from forensics.truvil.truvil_runtime import (
    DEFAULT_CLIP_LEN,
    DEFAULT_HEIGHT,
    DEFAULT_MAX_CLIPS,
    DEFAULT_SAMPLE_EVERY,
    DEFAULT_WIDTH,
    truvil_runtime_status,
)


class TruVilPlugin(ForensicPlugin):
    @property
    def name(self) -> str:
        return "truvil"

    @property
    def supported_types(self) -> list[str]:
        return ["video"]

    @classmethod
    def is_runtime_available(cls) -> Tuple[bool, str]:
        return truvil_runtime_status()

    def validate_parameters(self, parameters: Dict[str, Any]) -> Tuple[bool, str]:
        ok, reason = truvil_runtime_status()
        if not ok:
            return False, reason
        sample_every = int(parameters.get("sample_every", DEFAULT_SAMPLE_EVERY))
        if sample_every < 1 or sample_every > 60:
            return False, "sample_every deve estar entre 1 e 60"
        max_clips = int(parameters.get("max_clips", parameters.get("max_frames", DEFAULT_MAX_CLIPS)))
        if max_clips < 1 or max_clips > 128:
            return False, "max_clips deve estar entre 1 e 128"
        clip_len = int(parameters.get("clip_len", DEFAULT_CLIP_LEN))
        if clip_len != DEFAULT_CLIP_LEN:
            return False, f"clip_len deve ser {DEFAULT_CLIP_LEN} (protocolo oficial TruVIL)"
        return True, ""

    def analyze(self, evidence_path: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        on_progress = pop_progress_callback(parameters)
        ok, reason = truvil_runtime_status()
        if not ok:
            return {"success": False, "error": reason, "adapter": "truvil", "status": "unavailable"}
        try:
            out_dir = job_artifact_dir(parameters, fallback_subdir="truvil_tmp")
            analysis = run_truvil_analysis(
                evidence_path,
                sample_every=int(parameters.get("sample_every", DEFAULT_SAMPLE_EVERY)),
                max_clips=int(parameters.get("max_clips", parameters.get("max_frames", DEFAULT_MAX_CLIPS))),
                clip_len=int(parameters.get("clip_len", DEFAULT_CLIP_LEN)),
                input_height=int(parameters.get("input_height", DEFAULT_HEIGHT)),
                input_width=int(parameters.get("input_width", DEFAULT_WIDTH)),
                mask_threshold=float(parameters.get("mask_threshold", 0.5)),
                out_dir=out_dir,
                on_progress=on_progress,
            )
            json_path, txt_path = write_truvil_report(analysis, out_dir)
            result: Dict[str, Any] = {
                "success": True,
                "adapter": "truvil",
                "status": "completed",
                "mean_mask_ratio": analysis.mean_mask_ratio,
                "max_mask_ratio": analysis.max_mask_ratio,
                "max_start_frame": analysis.max_start_frame,
                "inference_device": analysis.inference_device,
                "truvil_report_json_path": json_path,
                "truvil_summary_txt_path": txt_path,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            if analysis.scores_chart_path:
                result["truvil_scores_chart_path"] = analysis.scores_chart_path
            if analysis.overlay_preview_path:
                result["truvil_overlay_preview_path"] = analysis.overlay_preview_path
            if analysis.mask_preview_path:
                result["truvil_mask_preview_path"] = analysis.mask_preview_path
            if analysis.heatmap_preview_path:
                result["truvil_heatmap_preview_path"] = analysis.heatmap_preview_path
            if analysis.input_preview_path:
                result["truvil_input_preview_path"] = analysis.input_preview_path
            report_progress(on_progress, 100, "Concluido")
            return result
        except Exception as exc:
            return {"success": False, "error": str(exc), "adapter": "truvil"}
