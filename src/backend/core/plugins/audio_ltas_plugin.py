"""LTAS — quatro graficos Welch (referencia MATLAB/Plotly)."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

from core.forensic_plugin import ForensicPlugin
from core.legacy.audio.audio_plotly_util import get_analyzer, write_plots
from core.plugins.audio_plugin_helpers import run_legacy


class AudioLTASPlugin(ForensicPlugin):
    @property
    def name(self) -> str:
        return "audio_ltas"

    @property
    def supported_types(self) -> list[str]:
        return ["audio"]

    def validate_parameters(self, parameters: Dict[str, Any]) -> Tuple[bool, str]:
        exp = int(parameters.get("fft_points", parameters.get("fft_exp", 12)))
        if not (8 <= exp <= 16):
            return False, "fft_points deve estar entre 8 e 16"
        canais = int(parameters.get("canais", 0))
        if canais not in (0, 1, 2):
            return False, "canais deve ser 0, 1 ou 2"
        return True, ""

    def analyze(self, evidence_path: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        try:
            fft_exp = int(parameters.get("fft_points", parameters.get("fft_exp", 12)))
            pts = int(parameters.get("nperseg", 2**fft_exp))
            canais = int(parameters.get("canais", 0))
            resample = parameters.get("resample_rate")
            resample_rate = float(resample) if resample not in (None, "", 0) else None

            def _run(wav_path: str, result_dir: Path) -> Dict[str, Any]:
                figs = get_analyzer().analyze_ltas(
                    wav_path, pts=pts, canais=canais, resample_rate=resample_rate
                )
                return write_plots(
                    [
                        ("ltas_normal", figs[0]),
                        ("ltas_6db", figs[1]),
                        ("ltas_sorted", figs[2]),
                        ("ltas_derivative", figs[3]),
                    ],
                    result_dir,
                )

            paths = run_legacy(evidence_path, parameters, self.name, _run)
            return {
                "success": True,
                "adapter": self.name,
                "status": "completed",
                "nperseg": pts,
                "canais": canais,
                "resample_rate": resample_rate,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                **paths,
            }
        except Exception as exc:
            return {"success": False, "error": str(exc), "adapter": self.name}
