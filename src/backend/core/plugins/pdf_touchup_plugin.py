"""PDF TouchUp_TextEdit detection plugin.

Wraps the legacy pdf_forensic_scanner that detects Adobe Acrobat
TouchUp_TextEdit marked content in page and Form XObject content streams.

This is a key tampering indicator: TouchUp_TextEdit regions indicate
manual text edits performed in Adobe Acrobat.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

from core.forensic_plugin import ForensicPlugin
from core.job_staging import job_artifact_dir

sys.path.insert(0, str(Path(__file__).parent.parent / "legacy" / "pdf"))
from pdf_forensic_scanner import scan_pdf_for_touchups


class PDFTouchupPlugin(ForensicPlugin):
    """Detect Adobe Acrobat TouchUp_TextEdit modifications in PDF."""

    @property
    def name(self) -> str:
        return "pdf_touchup"

    @property
    def supported_types(self) -> list[str]:
        return ["pdf"]

    def validate_parameters(self, parameters: Dict[str, Any]) -> Tuple[bool, str]:
        return True, ""

    def analyze(self, evidence_path: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        try:
            result_dir = job_artifact_dir(parameters, fallback_subdir="pdf_touchup")

            base_name = Path(evidence_path).stem
            out_pdf = result_dir / f"{base_name}_highlighted.pdf"
            out_txt = result_dir / f"{base_name}_touchup_text.txt"

            # Run legacy scanner
            touchups = scan_pdf_for_touchups(
                evidence_path,
                str(out_pdf),
                str(out_txt),
            )

            return {
                "success": True,
                "adapter": "pdf_touchup",
                "status": "completed",
                "touchup_count": len(touchups),
                "is_tampered": len(touchups) > 0,
                "touchups": [
                    {
                        "page": t[0],
                        "kind": t[1],
                        "text_preview": t[2][:200] if t[2] else "",
                        "rect": [t[3].x0, t[3].y0, t[3].x1, t[3].y1] if hasattr(t[3], "x0") else [],
                    }
                    for t in touchups[:50]  # limit detail
                ],
                "highlighted_pdf": str(out_pdf) if out_pdf.exists() else None,
                "extracted_text": str(out_txt) if out_txt.exists() else None,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
                "adapter": "pdf_touchup",
            }
