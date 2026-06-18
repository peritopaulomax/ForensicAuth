"""PDF structure metrics — grafo de objetos e metricas estruturais."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

from core.forensic_plugin import ForensicPlugin
from core.job_staging import job_artifact_dir
from core.legacy.pdf.pdf_structure_graph import analyze_pdf_structure


class PDFStructureMetricsPlugin(ForensicPlugin):
    @property
    def name(self) -> str:
        return "pdf_structure_metrics"

    @property
    def supported_types(self) -> list[str]:
        return ["pdf"]

    def validate_parameters(self, parameters: Dict[str, Any]) -> Tuple[bool, str]:
        return True, ""

    def analyze(self, evidence_path: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        tmpdir = job_artifact_dir(parameters, fallback_subdir="pdf_struct_tmp")
        try:
            out = analyze_pdf_structure(evidence_path, tmpdir)
            return {
                "success": True,
                "adapter": self.name,
                "status": "completed",
                "node_count": out.get("nodes"),
                "edge_count": out.get("edges"),
                "layout_engine": out.get("layout_engine"),
                "structure_graph_image_path": out.get("structure_graph_image_path"),
                "structure_graph_html_path": out.get("structure_graph_html_path"),
                "structure_graph_html_error": out.get("structure_graph_html_error"),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as exc:
            return {"success": False, "error": str(exc), "adapter": self.name}
