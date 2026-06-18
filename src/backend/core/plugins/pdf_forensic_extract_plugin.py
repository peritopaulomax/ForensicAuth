"""Extracao forense PDF: imagens, metadados, versoes incrementais."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

from core.forensic_plugin import ForensicPlugin
from core.job_staging import job_artifact_dir
from core.legacy.pdf.pdf_forensic_extract import run_pdf_forensic_extract


class PDFForensicExtractPlugin(ForensicPlugin):
    @property
    def name(self) -> str:
        return "pdf_forensic_extract"

    @property
    def supported_types(self) -> list[str]:
        return ["pdf"]

    def validate_parameters(self, parameters: Dict[str, Any]) -> Tuple[bool, str]:
        return True, ""

    def analyze(self, evidence_path: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        tmpdir = job_artifact_dir(parameters, fallback_subdir="pdf_forensic_extract_tmp")
        reporter = parameters.get("_progress_reporter")

        def report(pct: int, msg: str) -> None:
            if callable(reporter):
                reporter(pct, msg)

        try:
            out = run_pdf_forensic_extract(evidence_path, tmpdir, reporter=report)
            return {
                "success": True,
                "adapter": self.name,
                "status": "completed",
                "image_count": out.get("image_count", 0),
                "incremental_status": (out.get("incremental_analysis") or {}).get("status"),
                "incremental_message": (out.get("incremental_analysis") or {}).get("message"),
                "incremental_version_count": (out.get("incremental_analysis") or {}).get(
                    "version_count", 0
                ),
                "metadata_report_path": out.get("metadata_report_path"),
                "pdf_extract_metadata_json_path": out.get("metadata_json_path"),
                "incremental_report_path": out.get("incremental_report_path"),
                "extract_manifest_path": out.get("extract_manifest_path"),
                "extract_bundle_dir": out.get("extract_bundle_dir"),
                "images_manifest": out.get("images_manifest"),
                "version_files": out.get("version_files"),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as exc:
            return {"success": False, "error": str(exc), "adapter": self.name}
