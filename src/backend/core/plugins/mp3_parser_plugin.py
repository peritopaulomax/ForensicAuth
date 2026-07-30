"""MP3 forensic parser plugin.

Binary parser of MP3 frames, ID3 tags, VBR headers, and encoder signatures.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Tuple

from core.forensic_plugin import ForensicPlugin
from forensics.audio.container_parser_jobs import run_mp3_parser_job


class MP3ParserPlugin(ForensicPlugin):
    """Forensic MP3 parser — frame analysis, ID3 tags, VBR headers, encoder signatures."""

    @property
    def name(self) -> str:
        return "mp3_parser"

    @property
    def supported_types(self) -> list[str]:
        return ["audio"]

    def validate_parameters(self, parameters: Dict[str, Any]) -> Tuple[bool, str]:
        return True, ""

    def analyze(self, evidence_path: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        try:
            result = run_mp3_parser_job(evidence_path, parameters)
            result["timestamp"] = datetime.now(timezone.utc).isoformat()
            return result
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
                "adapter": "mp3_parser",
            }
