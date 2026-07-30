"""Extracao forense PDF: imagens, metadados, assinaturas, versoes incrementais."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Tuple

from core.forensic_plugin import ForensicPlugin
from core.job_staging import job_artifact_dir
from forensics.pdf.pdf_forensic_extract import run_pdf_forensic_extract


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
            sig = out.get("signatures_analysis") or {}
            first_sig = (sig.get("signatures") or [None])[0] or {}
            human = first_sig.get("human_verdict") or {}
            findings = sig.get("findings_summary") or {}
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
                "pdf_signed": out.get("pdf_signed", False),
                "signature_count": out.get("signature_count", 0),
                "signatures_status": sig.get("status"),
                "signatures_message": sig.get("message"),
                "signatures_findings_summary": findings,
                "signatures_pades_level": first_sig.get("pades_level"),
                "signatures_headline": human.get("headline"),
                "signatures_verdict": human,
                "signatures_dss_present": bool((sig.get("document_dss") or {}).get("present")),
                "signatures_anchor_mode": sig.get("anchor_mode"),
                "signatures_anchors_from_file": bool(sig.get("anchors_from_file")),
                "signatures_has_critical": bool(sig.get("has_critical")),
                "metadata_report_path": out.get("metadata_report_path"),
                "pdf_extract_metadata_json_path": out.get("metadata_json_path"),
                "incremental_report_path": out.get("incremental_report_path"),
                "signatures_json_path": out.get("signatures_json_path"),
                "signatures_report_path": out.get("signatures_report_path"),
                "extract_manifest_path": out.get("extract_manifest_path"),
                "extract_bundle_dir": out.get("extract_bundle_dir"),
                "images_manifest": out.get("images_manifest"),
                "version_files": out.get("version_files"),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as exc:
            return {"success": False, "error": str(exc), "adapter": self.name}
