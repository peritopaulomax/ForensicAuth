"""Parser estrutural ISO BMFF para videos questionados."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

from core.forensic_plugin import ForensicPlugin
from core.job_staging import job_artifact_dir
from core.legacy.video.isom_parser import run_isomedia_parser


class ISOMediaParserPlugin(ForensicPlugin):
    @property
    def name(self) -> str:
        return "isomedia_parser"

    @property
    def supported_types(self) -> list[str]:
        return ["video"]

    def validate_parameters(self, parameters: Dict[str, Any]) -> Tuple[bool, str]:
        return True, ""

    def analyze(self, evidence_path: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        tmpdir = job_artifact_dir(parameters, fallback_subdir="isom_parser_tmp")
        reporter = parameters.get("_progress_reporter")

        def report(pct: int, msg: str) -> None:
            if callable(reporter):
                reporter(pct, msg)

        try:
            out = run_isomedia_parser(evidence_path, tmpdir, reporter=report)
            return {
                "success": True,
                "adapter": self.name,
                "status": "completed",
                "box_count": out.get("box_count"),
                "depth": out.get("depth"),
                "tree": out.get("tree"),
                "metadata": out.get("metadata"),
                "udta_atoms": out.get("udta_atoms"),
                "meta_atoms": out.get("meta_atoms"),
                "isom_structure_graph_path": out.get("isom_structure_graph_path"),
                "isom_tree_json_path": out.get("isom_tree_json_path"),
                "isom_tree_txt_path": out.get("isom_tree_txt_path"),
                "isom_metadata_json_path": out.get("isom_metadata_json_path"),
                "isom_metadata_txt_path": out.get("isom_metadata_txt_path"),
                "isom_udta_json_path": out.get("isom_udta_json_path"),
                "isom_meta_atoms_json_path": out.get("isom_meta_atoms_json_path"),
                "metadata_report_path": out.get("metadata_report_path"),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as exc:
            return {"success": False, "error": str(exc), "adapter": self.name}
