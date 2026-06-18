"""Tests for audio forensic plugins — legado Gradio / AudioForensicsAnalyzer."""

import os
import struct
import tempfile

import numpy as np
import pytest
from scipy.io import wavfile


@pytest.fixture
def sample_wav():
    """Synthetic WAV with ~60 Hz tone for ENF."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        sr = 8000
        t = np.linspace(0, 2, sr * 2)
        signal = 0.5 * np.sin(2 * np.pi * 60 * t) + 0.05 * np.random.randn(len(t))
        signal = (signal * 32767).astype(np.int16)
        wavfile.write(f.name, sr, signal)
        yield f.name
    os.unlink(f.name)


@pytest.fixture
def sample_mp3():
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        header = struct.pack(">H", 0xFFFB)
        header += struct.pack(">H", 0x9000)
        f.write(header)
        f.write(b"\x00" * 400)
        yield f.name
    os.unlink(f.name)


class TestAudioENF:
    def test_enf_legacy_plot(self, sample_wav):
        from core.plugins.audio_enf_plugin import AudioENFPlugin

        plugin = AudioENFPlugin()
        result = plugin.analyze(sample_wav, {"fnom": 60, "bwenf": 0.8})
        assert result["success"] is True
        assert os.path.exists(result["interactive_html_path"])

    def test_enf_custom_freq(self, sample_wav):
        from core.plugins.audio_enf_plugin import AudioENFPlugin

        plugin = AudioENFPlugin()
        valid, _ = plugin.validate_parameters({"fnom": 55, "bwenf": 0.8})
        assert valid is True
        result = plugin.analyze(sample_wav, {"fnom": 55, "bwenf": 0.8})
        assert result["success"] is True
        assert result["fnom"] == 55

    def test_enf_invalid_freq(self):
        from core.plugins.audio_enf_plugin import AudioENFPlugin

        plugin = AudioENFPlugin()
        valid, msg = plugin.validate_parameters({"fnom": 350})
        assert valid is False
        assert "300" in msg


class TestAudioSpectrogram:
    def test_spectrogram_html(self, sample_wav):
        from core.plugins.audio_spectrogram_plugin import AudioSpectrogramPlugin

        plugin = AudioSpectrogramPlugin()
        result = plugin.analyze(
            sample_wav,
            {"fft_points": 10, "window_type": "hamming", "window_size_percent": 75},
        )
        assert result["success"] is True
        assert result["n_fft"] == 1024
        assert os.path.exists(result["interactive_html_path"])
        assert os.path.exists(result["spectrogram_path"])
        assert "display_decimation" in result


class TestAudioLTAS:
    def test_ltas_four_plots(self, sample_wav):
        from core.plugins.audio_ltas_plugin import AudioLTASPlugin

        plugin = AudioLTASPlugin()
        result = plugin.analyze(sample_wav, {"fft_points": 10, "nperseg": 1024, "canais": 0})
        assert result["success"] is True
        for key in (
            "ltas_normal_html_path",
            "ltas_6db_html_path",
            "ltas_sorted_html_path",
            "ltas_derivative_html_path",
        ):
            assert os.path.exists(result[key])


class TestAudioLevels:
    def test_levels_html(self, sample_wav):
        from core.plugins.audio_levels_plugin import AudioLevelsPlugin

        plugin = AudioLevelsPlugin()
        result = plugin.analyze(sample_wav, {"bitdepth": 16, "canais": 0})
        assert result["success"] is True
        assert os.path.exists(result["interactive_html_path"])


class TestAudioDCLocal:
    def test_dc_html(self, sample_wav):
        from core.plugins.audio_dc_local_plugin import AudioDCLocalPlugin

        plugin = AudioDCLocalPlugin()
        result = plugin.analyze(sample_wav, {"dur": 1.0})
        assert result["success"] is True
        assert os.path.exists(result["interactive_html_path"])


class TestMP3Parser:
    def test_mp3_parser_runs(self, sample_mp3):
        from core.plugins.mp3_parser_plugin import MP3ParserPlugin

        plugin = MP3ParserPlugin()
        result = plugin.analyze(sample_mp3, {})
        assert "success" in result


class TestAudioPluginsList:
    def test_all_audio_plugins_registered(self):
        from core.plugin_registry import PluginRegistry

        registry = PluginRegistry()
        from pathlib import Path

        plugins_dir = Path(__file__).resolve().parents[2] / "src" / "backend" / "core" / "plugins"
        registry.discover_and_register(str(plugins_dir))
        audio_plugins = [
            n
            for n in registry.PLUGINS.keys()
            if n.startswith(("mp3_", "opus_", "wav_", "audio_"))
        ]
        assert "audio_enf" in audio_plugins
        assert "audio_levels" in audio_plugins
        assert "audio_dc_local" in audio_plugins
        assert len(audio_plugins) >= 6
