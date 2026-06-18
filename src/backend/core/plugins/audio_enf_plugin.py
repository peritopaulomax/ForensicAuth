"""ENF — deteccao via FIR + Hilbert + Plotly."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

from core.forensic_plugin import ForensicPlugin
from core.legacy.audio.audio_plotly_util import get_analyzer, write_plot_html, write_plot_traces_json
from core.plugins.audio_plugin_helpers import run_legacy

FNOM_MIN_HZ = 1.0
FNOM_MAX_HZ = 300.0


class AudioENFPlugin(ForensicPlugin):
    @property
    def name(self) -> str:
        return "audio_enf"

    @property
    def supported_types(self) -> list[str]:
        return ["audio"]

    def validate_parameters(self, parameters: Dict[str, Any]) -> Tuple[bool, str]:
        fnom = float(
            parameters.get(
                "fnom",
                parameters.get("target_freq", parameters.get("frequency", 60)),
            )
        )
        if not (FNOM_MIN_HZ <= fnom <= FNOM_MAX_HZ):
            return (
                False,
                f"fnom (frequencia nominal) deve estar entre {FNOM_MIN_HZ:g} e {FNOM_MAX_HZ:g} Hz",
            )
        bw = float(parameters.get("bwenf", parameters.get("bandwidth", 0.8)))
        if not (0.1 <= bw <= 2.0):
            return False, "bwenf deve estar entre 0.1 e 2.0 Hz"
        return True, ""

    def analyze(self, evidence_path: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        try:
            fnom = float(
                parameters.get(
                    "fnom",
                    parameters.get("target_freq", parameters.get("frequency", 60)),
                )
            )
            bwenf = float(parameters.get("bwenf", parameters.get("bandwidth", 0.8)))

            def _run(wav_path: str, result_dir: Path) -> Dict[str, Any]:
                fig = get_analyzer().calculate_enf_deviation(wav_path, fnom=fnom, bwenf=bwenf)
                html_path = result_dir / "interactive.html"
                write_plot_html(fig, html_path, div_id="audio-enf")
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
                "fnom": fnom,
                "bwenf": bwenf,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                **paths,
            }
        except Exception as exc:
            return {"success": False, "error": str(exc), "adapter": self.name}
