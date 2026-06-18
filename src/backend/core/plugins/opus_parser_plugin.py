"""Opus forensic parser plugin.

Wraps the legacy OpusAnalyzer that performs pure binary parsing
of Ogg/Opus pages, headers, TOC bytes, and platform signatures.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

from core.forensic_plugin import ForensicPlugin

sys.path.insert(0, str(Path(__file__).parent.parent / "legacy" / "audio"))
from opus_parser import OggOpusAnalyzer as OpusAnalyzer


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
            analyzer = OpusAnalyzer(evidence_path)
            analyzer.parse()

            return {
                "success": True,
                "adapter": "opus_parser",
                "status": "completed",
                "pages": [p.__dict__ for p in analyzer.pages] if hasattr(analyzer, "pages") else [],
                "id_header": analyzer.id_header.__dict__ if hasattr(analyzer, "id_header") and analyzer.id_header else {},
                "comment_header": analyzer.comment_header.__dict__ if hasattr(analyzer, "comment_header") and analyzer.comment_header else {},
                "platform_guess": analyzer.platform_guess if hasattr(analyzer, "platform_guess") else "unknown",
                "toc_analysis": analyzer.toc_analysis if hasattr(analyzer, "toc_analysis") else [],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
                "adapter": "opus_parser",
            }
