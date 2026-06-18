"""PDF font color overlay — retangulos por recurso de fonte."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

from core.forensic_plugin import ForensicPlugin
from core.job_staging import job_artifact_dir
from core.legacy.pdf.pdf_font_color_overlay import run_font_color_overlay


class PDFFontColorOverlayPlugin(ForensicPlugin):
    @property
    def name(self) -> str:
        return "pdf_font_color_overlay"

    @property
    def supported_types(self) -> list[str]:
        return ["pdf"]

    def validate_parameters(self, parameters: Dict[str, Any]) -> Tuple[bool, str]:
        op = float(parameters.get("opacity", 0.42))
        if not 0.05 <= op <= 1.0:
            return False, "opacity deve estar entre 0.05 e 1.0"
        return True, ""

    def analyze(self, evidence_path: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        opacity = float(parameters.get("opacity", 0.42))
        by_subset = parameters.get("by_subset", False)
        if isinstance(by_subset, str):
            by_subset = by_subset.lower() not in ("0", "false", "no")

        tmpdir = job_artifact_dir(parameters, fallback_subdir="pdf_fontmap_tmp")
        out_pdf = tmpdir / "font_overlay.pdf"
        out_txt = tmpdir / "font_legend.txt"
        try:
            meta = run_font_color_overlay(
                evidence_path,
                out_pdf,
                out_txt,
                opacity=opacity,
                by_subset=bool(by_subset),
            )
            legend_text = out_txt.read_text(encoding="utf-8") if out_txt.exists() else ""
            return {
                "success": True,
                "adapter": self.name,
                "status": "completed",
                "overlay_pdf_path": str(out_pdf),
                "legend_txt_path": str(out_txt),
                "legend_preview": legend_text[:4000],
                "fonts_count": meta.get("fonts_count"),
                "rectangles": meta.get("rectangles"),
                "fonts": meta.get("fonts"),
                "mode": meta.get("mode"),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as exc:
            return {"success": False, "error": str(exc), "adapter": self.name}
