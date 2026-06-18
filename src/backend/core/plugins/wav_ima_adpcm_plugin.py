"""WAV IMA ADPCM consistency plugin.

Wraps the legacy WAV IMA ADPCM parser that decodes block headers,
simulates nibble processing, and detects step_index inconsistencies
between sequential blocks.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

from core.forensic_plugin import ForensicPlugin

sys.path.insert(0, str(Path(__file__).parent.parent / "legacy" / "audio"))
from wav_ima_adpcm import read_wave_ima_adpcm


class WAVIMAADPCMPlugin(ForensicPlugin):
    """WAV IMA ADPCM consistency checker — detects tampering via index mismatches."""

    @property
    def name(self) -> str:
        return "wav_ima_adpcm"

    @property
    def supported_types(self) -> list[str]:
        return ["audio"]

    def validate_parameters(self, parameters: Dict[str, Any]) -> Tuple[bool, str]:
        return True, ""

    def analyze(self, evidence_path: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        try:
            result = read_wave_ima_adpcm(evidence_path)

            inconsistencies = result.get("inconsistencies", [])
            total_blocks = result.get("total_blocks", 0)

            return {
                "success": True,
                "adapter": "wav_ima_adpcm",
                "status": "completed",
                "total_blocks": total_blocks,
                "inconsistency_count": len(inconsistencies),
                "inconsistency_percentage": (len(inconsistencies) / max(total_blocks, 1)) * 100,
                "inconsistencies": inconsistencies[:100],  # limit detail
                "is_tampered": len(inconsistencies) > 0,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
                "adapter": "wav_ima_adpcm",
            }
