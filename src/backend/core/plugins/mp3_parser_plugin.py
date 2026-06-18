"""MP3 forensic parser plugin.

Wraps the legacy MP3Analyzer that performs pure binary parsing
of MP3 frames, ID3 tags, VBR headers, and encoder signatures.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

from core.forensic_plugin import ForensicPlugin

# Import legacy parser
sys.path.insert(0, str(Path(__file__).parent.parent / "legacy" / "audio"))
from mp3_parser import MP3Analyzer


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
            analyzer = MP3Analyzer(evidence_path)
            analyzer.parse()

            return {
                "success": True,
                "adapter": "mp3_parser",
                "status": "completed",
                "file_info": analyzer.get_file_info(),
                "frames": [f.__dict__ for f in analyzer.frames],
                "id3v1": analyzer.id3v1_tags if hasattr(analyzer, "id3v1_tags") else {},
                "id3v2": analyzer.id3v2_tags if hasattr(analyzer, "id3v2_tags") else {},
                "vbr_header": analyzer.vbr_header if hasattr(analyzer, "vbr_header") else None,
                "encoder": analyzer.encoder_signature if hasattr(analyzer, "encoder_signature") else "unknown",
                "inconsistencies": analyzer.inconsistencies if hasattr(analyzer, "inconsistencies") else [],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
                "adapter": "mp3_parser",
            }
