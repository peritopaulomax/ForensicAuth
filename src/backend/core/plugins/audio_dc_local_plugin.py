"""Nivel DC local por janela temporal."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

from core.forensic_plugin import ForensicPlugin
from core.legacy.audio.audio_plotly_util import get_analyzer, write_plot_html, write_plot_traces_json
from core.plugins.audio_plugin_helpers import run_legacy


class AudioDCLocalPlugin(ForensicPlugin):
    @property
    def name(self) -> str:
        return "audio_dc_local"

    @property
    def supported_types(self) -> list[str]:
        return ["audio"]

    def validate_parameters(self, parameters: Dict[str, Any]) -> Tuple[bool, str]:
        dur = float(parameters.get("dur", parameters.get("window_duration_s", 5.0)))
        if dur <= 0:
            return False, "dur (duracao da janela) deve ser positiva"
        return True, ""

    def analyze(self, evidence_path: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        try:
            dur = float(parameters.get("dur", parameters.get("window_duration_s", 5.0)))

            def _run(wav_path: str, result_dir: Path) -> Dict[str, Any]:
                fig = get_analyzer().analyze_local_dc(wav_path, dur=dur)
                html_path = result_dir / "interactive.html"
                write_plot_html(fig, html_path, div_id="audio-dc")
                traces_path = result_dir / "plot_traces.json"
                write_plot_traces_json(fig, traces_path)
                return {
                    "interactive_html_path": str(html_path),
                    "plot_traces_json_path": str(traces_path),
                }

            paths = run_legacy(evidence_path, parameters, self.name, _run)
            return {
                "success": True,
                "adapter": self.name,
                "status": "completed",
                "dur": dur,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                **paths,
            }
        except Exception as exc:
            return {"success": False, "error": str(exc), "adapter": self.name}
