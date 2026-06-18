"""Espectrograma forense — scipy.signal.spectrogram + Plotly."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

import numpy as np

from core.forensic_plugin import ForensicPlugin
from core.legacy.audio.audio_plotly_util import get_analyzer, write_plot_html
from core.legacy.audio.spectrogram_export import write_spectrogram_png
from core.legacy.audio.spectrogram_scipy import load_mono_audio
from core.plugins.audio_plugin_helpers import run_legacy
from core.progress import pop_progress_callback, report_progress


class AudioSpectrogramPlugin(ForensicPlugin):
    @property
    def name(self) -> str:
        return "audio_spectrogram"

    @property
    def supported_types(self) -> list[str]:
        return ["audio"]

    def validate_parameters(self, parameters: Dict[str, Any]) -> Tuple[bool, str]:
        window = parameters.get("window_type", parameters.get("window", "hamming"))
        allowed = ("hamming", "hanning", "blackman", "blackmanharris", "kaiser")
        if window not in allowed:
            return False, f"window_type deve ser um de: {', '.join(allowed)}"
        exp = int(parameters.get("fft_points", parameters.get("fft_exp", 10)))
        if not (7 <= exp <= 16):
            return False, "fft_points deve estar entre 7 e 16 (128 a 65536 pontos, 2^N)"
        return True, ""

    def analyze(self, evidence_path: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        try:
            fft_exp = int(parameters.get("fft_points", parameters.get("fft_exp", 10)))
            window_type = parameters.get("window_type", parameters.get("window", "hamming"))
            window_size_percent = float(parameters.get("window_size_percent", 75))
            resample = parameters.get("resample_rate")
            resample_rate = float(resample) if resample not in (None, "", 0) else None

            progress_cb = pop_progress_callback(parameters)

            def _run(wav_path: str, result_dir: Path) -> Dict[str, Any]:
                report_progress(progress_cb, 10, "Carregando audio…")
                audio, sr = load_mono_audio(wav_path, resample_rate)

                def job_progress(pct: int, msg: str) -> None:
                    report_progress(progress_cb, pct, msg)

                out = get_analyzer().analyze_spectrogram(
                    wav_path,
                    fft_points=fft_exp,
                    window_type=window_type,
                    window_size_percent=window_size_percent,
                    resample_rate=resample_rate,
                    decimate_display=False,
                    progress_callback=job_progress,
                    _preloaded_audio=audio,
                    _preloaded_sr=sr,
                )
                if out.get("error"):
                    raise RuntimeError(out["error"])

                report_progress(progress_cb, 72, "Gerando HTML interativo…")
                fig = out["figure"]
                html_path = result_dir / "interactive.html"
                write_plot_html(fig, html_path, div_id="audio-spectrogram")

                report_progress(progress_cb, 78, "Exportando PNG…")
                png_path = result_dir / "spectrogram.png"
                write_spectrogram_png(
                    out["magnitude_db_display"],
                    out["times_display"],
                    out["frequencies_display"],
                    png_path,
                    title=f"Espectrograma — {window_type}",
                )

                report_progress(progress_cb, 82, "Salvando NPZ…")
                npz_path = result_dir / "spectrogram_full.npz"
                np.savez_compressed(
                    npz_path,
                    frequencies_display=np.asarray(out["frequencies_display"], dtype=np.float32),
                    times_display=np.asarray(out["times_display"], dtype=np.float32),
                    magnitude_db_display=np.asarray(out["magnitude_db_display"], dtype=np.float32),
                    sample_rate=np.int32(out["sample_rate"]),
                    n_fft=np.int32(out["n_fft"]),
                    hop_length=np.int32(out["hop_length"]),
                    stft_shape=np.asarray(out["stft_meta"].get("shape", [0, 0]), dtype=np.int32),
                    duration_sec=np.float32(out["stft_meta"].get("duration_sec", 0)),
                    hop_adjusted=np.bool_(out["stft_meta"].get("hop_adjusted", False)),
                )

                return {
                    "interactive_html_path": str(html_path),
                    "spectrogram_png_path": str(png_path),
                    "spectrogram_path": str(npz_path),
                    "display_decimation": out["display_decimation"],
                    "stft_meta": out["stft_meta"],
                }

            paths = run_legacy(evidence_path, parameters, self.name, _run)
            decimation = paths.get("display_decimation") or {}
            stft_meta = paths.get("stft_meta") or {}
            return {
                "success": True,
                "adapter": self.name,
                "status": "completed",
                "fft_points": fft_exp,
                "n_fft": 2**fft_exp,
                "window_type": window_type,
                "window_size_percent": window_size_percent,
                "resample_rate": resample_rate,
                "display_decimation": decimation,
                "stft_meta": stft_meta,
                "time_frames": stft_meta.get("shape", [0, 0])[1] if stft_meta.get("shape") else decimation.get("full_shape", [0, 0])[1],
                "freq_bins": stft_meta.get("shape", [0, 0])[0] if stft_meta.get("shape") else decimation.get("full_shape", [0, 0])[0],
                "npz_note": "Grade STFT completa; decimacao opcional apenas na visualizacao do cliente.",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                **{k: v for k, v in paths.items() if k not in ("display_decimation", "stft_meta")},
            }
        except Exception as exc:
            return {"success": False, "error": str(exc), "adapter": self.name}
