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


class TestAudioSpoofingDetection:
    def test_adapter_registered_and_has_expected_name(self):
        from core.plugin_registry import PluginRegistry
        from core.plugins.audio_spoofing_adapter import AudioSpoofingAdapter

        registry = PluginRegistry()
        from pathlib import Path

        plugins_dir = Path(__file__).resolve().parents[2] / "src" / "backend" / "core" / "plugins"
        registry.discover_and_register(str(plugins_dir))
        assert "audio_spoofing_detection" in registry.PLUGINS
        plugin = AudioSpoofingAdapter()
        assert plugin.name == "audio_spoofing_detection"
        assert "audio" in plugin.supported_types

    def test_adapter_validates_window_seconds(self):
        from core.plugins.audio_spoofing_adapter import AudioSpoofingAdapter

        plugin = AudioSpoofingAdapter()
        valid, _ = plugin.validate_parameters({"window_seconds": 4.0})
        assert valid is True
        valid, msg = plugin.validate_parameters({"window_seconds": 0.5})
        assert valid is False
        assert "1" in msg

    def test_adapter_returns_failure_without_model(self, sample_wav, monkeypatch):
        from core.plugins import audio_spoofing_adapter as adapter_mod

        plugin = adapter_mod.AudioSpoofingAdapter()
        monkeypatch.setattr(adapter_mod, "runtime_status", lambda: (False, "mock indisponivel"))
        result = plugin.analyze(sample_wav, {})
        assert result["success"] is False
        assert "indisponivel" in result["error"].lower()

    def test_adapter_validates_max_duration(self):
        from core.plugins.audio_spoofing_adapter import AudioSpoofingAdapter

        plugin = AudioSpoofingAdapter()
        valid, _ = plugin.validate_parameters({"max_duration_seconds": 90.0})
        assert valid is True
        valid, msg = plugin.validate_parameters({"max_duration_seconds": 5.0})
        assert valid is False
        assert "10" in msg

    def test_adapter_limits_audio_to_90_seconds(self, sample_wav, monkeypatch):
        from core.plugins import audio_spoofing_adapter as adapter_mod

        calls = []

        def fake_run(audio, sr, window_seconds=4.0, selected_analyses=None, on_progress=None):
            calls.append(len(audio))
            return {
                "individual_results": [["DF Arena 1B", "0.5", "0.5", "0.00", "Incerto", "cpu"]],
                "detector_scores": {
                    "df_arena_1b": {
                        "spoof_prob": 0.5,
                        "bonafide_prob": 0.5,
                        "label": "uncertain",
                        "window_count": 1,
                    }
                },
                "per_detector": {},
                "plot_by_detector": {},
                "selected_analyses": ["df_arena_1b"],
                "inference_device": "cpu",
                "label": "uncertain",
                "score_spoof": 0.5,
                "score_bonafide": 0.5,
                "window_count": 1,
            }

        plugin = adapter_mod.AudioSpoofingAdapter()
        monkeypatch.setattr(adapter_mod, "run_audio_spoofing_analysis", fake_run)
        result = plugin.analyze(sample_wav, {"selected_analyses": ["df_arena_1b"]})
        assert result["success"] is True
        assert calls[0] <= 720000
        assert result["detector_scores_filename"] == "detector_scores.txt"

    def test_adapter_validates_selected_analyses(self, monkeypatch):
        from core.plugins import audio_spoofing_adapter as adapter_mod
        from core.legacy.audio_spoofing import runtime as spoof_runtime

        monkeypatch.setattr(spoof_runtime, "runtime_status", lambda: (True, ""))
        monkeypatch.setattr(
            spoof_runtime,
            "detector_runtime_status",
            lambda detector_id: (
                (True, "")
                if detector_id in {"df_arena_1b", "sls_xlsr", "wedefense_wavlm_mhfa"}
                else (False, "x")
            ),
        )
        plugin = adapter_mod.AudioSpoofingAdapter()
        ok, _ = plugin.validate_parameters({
            "selected_analyses": ["df_arena_1b", "sls_xlsr", "wedefense_wavlm_mhfa"],
        })
        assert ok is True
        ok, msg = plugin.validate_parameters({"selected_analyses": []})
        assert ok is False
        ok, msg = plugin.validate_parameters({"selected_analyses": ["nao_existe"]})
        assert ok is False
        assert "invalidos" in msg.lower()

    def test_adapter_multi_detector_mock(self, sample_wav, monkeypatch):
        from core.plugins import audio_spoofing_adapter as adapter_mod

        def fake_run(audio, sr, window_seconds=4.0, selected_analyses=None, on_progress=None):
            return {
                "individual_results": [
                    ["DF Arena 1B", "0.70", "0.30", "-0.37", "Spoof", "cpu"],
                    ["SLS XLS-R (ACM MM 2024)", "0.40", "0.60", "0.18", "Incerto", "cpu"],
                ],
                "detector_scores": {
                    "df_arena_1b": {"spoof_prob": 0.7, "bonafide_prob": 0.3, "label": "spoof"},
                    "sls_xlsr": {"spoof_prob": 0.4, "bonafide_prob": 0.6, "label": "uncertain"},
                },
                "per_detector": {},
                "plot_by_detector": {
                    "df_arena_1b": {"centers": [2.0], "spoof_probs": [0.7], "bonafide_probs": [0.3], "window_seconds": 4.0},
                    "sls_xlsr": {"centers": [2.0], "spoof_probs": [0.4], "bonafide_probs": [0.6], "window_seconds": 4.0},
                },
                "selected_analyses": ["df_arena_1b", "sls_xlsr"],
                "inference_device": "cpu",
                "label": "spoof",
                "score_spoof": 0.7,
                "score_bonafide": 0.3,
                "window_count": 1,
            }

        plugin = adapter_mod.AudioSpoofingAdapter()
        monkeypatch.setattr(adapter_mod, "run_audio_spoofing_analysis", fake_run)
        result = plugin.analyze(sample_wav, {"selected_analyses": ["df_arena_1b", "sls_xlsr"]})
        assert result["success"] is True
        assert len(result["individual_results"]) == 2
        assert "df_arena_1b" in result["detector_scores"]
        assert "sls_xlsr" in result["detector_scores"]
        assert "plot_by_detector" in result["plot_data"]


class TestWeDefenseLogitMapping:
    def test_wedefense_logits_map_bonafide_idx0_spoof_idx1(self):
        from core.legacy.wedefense_spoofing.wedefense_pipeline import _wedefense_probs_to_scores
        import numpy as np

        logits = np.array([2.0, -1.0])
        spoof_log, bonafide_log, spoof_prob, bonafide_prob = _wedefense_probs_to_scores(logits)
        assert bonafide_log == 2.0
        assert spoof_log == -1.0
        assert bonafide_prob > spoof_prob


class TestSLSSpoofingPaths:
    def test_models_dir_resolves_relative_models_dir_from_backend_cwd(self, monkeypatch):
        from pathlib import Path

        from app.config import get_settings
        import core.legacy.sls_spoofing.sls_runtime as sls_runtime

        backend_cwd = Path(__file__).resolve().parents[2] / "src" / "backend"
        monkeypatch.chdir(backend_cwd)
        monkeypatch.setenv("MODELS_DIR", "../../models")
        get_settings.cache_clear()

        models_dir = sls_runtime._models_dir()
        workspace = sls_runtime._workspace_root()
        assert models_dir == (workspace / "models" / "sls_spoofing").resolve()
        get_settings.cache_clear()


class TestDFArenaAggregation:
    def test_aggregated_label_uncertain_when_both_below_or_equal_threshold(self):
        from core.legacy.df_arena.df_arena_pipeline import _softmax, UNCERTAINTY_THRESHOLD
        import numpy as np

        # Both probabilities below or equal to threshold -> uncertain
        logits = np.array([0.2, 0.1])
        probs = _softmax(logits)
        assert probs[0] <= UNCERTAINTY_THRESHOLD
        assert probs[1] <= UNCERTAINTY_THRESHOLD

    def test_aggregated_label_spoof_when_spoof_above_threshold(self):
        from core.legacy.df_arena.df_arena_pipeline import _softmax, UNCERTAINTY_THRESHOLD
        import numpy as np

        logits = np.array([2.0, -1.0])
        probs = _softmax(logits)
        assert probs[0] > UNCERTAINTY_THRESHOLD

    def test_aggregated_label_bonafide_when_bonafide_above_threshold(self):
        from core.legacy.df_arena.df_arena_pipeline import _softmax, UNCERTAINTY_THRESHOLD
        import numpy as np

        logits = np.array([-1.0, 2.0])
        probs = _softmax(logits)
        assert probs[1] > UNCERTAINTY_THRESHOLD

    def test_aggregated_label_uncertain_when_both_probabilities_below_65(self):
        from core.legacy.df_arena.df_arena_pipeline import _softmax, UNCERTAINTY_THRESHOLD
        import numpy as np

        # logits that yield ~40% spoof / ~60% bonafide (both strictly below 65%)
        logits = np.array([0.4, 0.8])
        probs = _softmax(logits)
        assert probs[0] < UNCERTAINTY_THRESHOLD
        assert probs[1] < UNCERTAINTY_THRESHOLD


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
        assert "audio_spoofing_detection" in audio_plugins
        assert len(audio_plugins) >= 5
