"""Opus forensic parser plugin.

Binary parser of Ogg/Opus pages, headers, TOC bytes, and platform signatures.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Tuple

from core.forensic_plugin import ForensicPlugin
from forensics.audio.container_parser_jobs import run_opus_parser_job


class OpusParserPlugin(ForensicPlugin):
    """Forensic Opus parser — Ogg page structure, OpusHead, OpusTags, TOC analysis."""

    @property
    def name(self) -> str:
        return "opus_parser"

    @property
    def supported_types(self) -> list[str]:
        return ["audio"]

    def validate_parameters(self, parameters: Dict[str, Any]) -> Tuple[bool, str]:
        return True, ""

    def analyze(self, evidence_path: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        try:
            result = run_opus_parser_job(evidence_path, parameters)
            result["timestamp"] = datetime.now(timezone.utc).isoformat()
            return result
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
                "adapter": "opus_parser",
            }
