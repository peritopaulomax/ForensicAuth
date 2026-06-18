"""Histograma de niveis de quantizacao PCM."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

from core.forensic_plugin import ForensicPlugin
from core.legacy.audio.audio_plotly_util import get_analyzer, write_plot_html, write_plot_traces_json
from core.plugins.audio_plugin_helpers import run_legacy


class AudioLevelsPlugin(ForensicPlugin):
    @property
    def name(self) -> str:
        return "audio_levels"

    @property
    def supported_types(self) -> list[str]:
        return ["audio"]

    def validate_parameters(self, parameters: Dict[str, Any]) -> Tuple[bool, str]:
        bitdepth = int(parameters.get("bitdepth", 16))
        if bitdepth not in (8, 16, 24, 32):
            return False, "bitdepth deve ser 8, 16, 24 ou 32"
        canais = int(parameters.get("canais", 0))
        if canais not in (0, 1, 2):
            return False, "canais deve ser 0, 1 ou 2"
        return True, ""

    def analyze(self, evidence_path: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        try:
            bitdepth = int(parameters.get("bitdepth", 16))
            canais = int(parameters.get("canais", 0))

            def _run(wav_path: str, result_dir: Path) -> Dict[str, Any]:
                fig = get_analyzer().analyze_quantization_levels(
                    wav_path, bitdepth=bitdepth, canais=canais
                )
                html_path = result_dir / "interactive.html"
                write_plot_html(fig, html_path, div_id="audio-levels")
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
                "bitdepth": bitdepth,
                "canais": canais,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                **paths,
            }
        except Exception as exc:
            return {"success": False, "error": str(exc), "adapter": self.name}
