"""Tests for audio forensic plugins (AudioForensicsAnalyzer / hub)."""

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
        f.flush()
        path = f.name
    yield path
    os.unlink(path)


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
    def test_mp3_parser_runs(self, sample_mp3, tmp_path):
        from core.plugins.mp3_parser_plugin import MP3ParserPlugin

        plugin = MP3ParserPlugin()
        result = plugin.analyze(sample_mp3, {"_job_staging_dir": str(tmp_path / "mp3_out")})
        assert result["success"] is True
        assert result["report"]
        assert "frame_count" in result
        assert os.path.exists(result["container_report_txt_path"])
        assert os.path.exists(result["container_summary_json_path"])


@pytest.fixture
def sample_opus():
    """Minimal Ogg page with OpusHead (BOS) for structural parse smoke test."""
    opus_head = bytearray(b"OpusHead")
    opus_head += struct.pack("<B", 1)  # version
    opus_head += struct.pack("<B", 1)  # channels
    opus_head += struct.pack("<H", 312)  # pre_skip
    opus_head += struct.pack("<I", 48000)  # input sample rate
    opus_head += struct.pack("<h", 0)  # output gain
    opus_head += struct.pack("<B", 0)  # channel mapping
    assert len(opus_head) == 19

    segment_table = bytes([len(opus_head)])
    header = bytearray(b"OggS")
    header += struct.pack("<B", 0)  # version
    header += struct.pack("<B", 0x02)  # BOS
    header += struct.pack("<Q", 0)  # granule
    header += struct.pack("<I", 0x12345678)  # serial
    header += struct.pack("<I", 0)  # sequence
    header += struct.pack("<I", 0)  # checksum placeholder
    header += struct.pack("<B", 1)  # nsegments
    header += segment_table
    page = bytes(header) + bytes(opus_head)

    fd, path = tempfile.mkstemp(suffix=".opus")
    try:
        os.write(fd, page)
    finally:
        os.close(fd)
    yield path
    os.unlink(path)


class TestOpusParser:
    def test_opus_parser_runs(self, sample_opus, tmp_path):
        from core.plugins.opus_parser_plugin import OpusParserPlugin

        plugin = OpusParserPlugin()
        result = plugin.analyze(sample_opus, {"_job_staging_dir": str(tmp_path / "opus_out")})
        assert result["success"] is True
        assert result["report"]
        assert result["page_count"] >= 1
        assert os.path.exists(result["container_report_txt_path"])
        assert "OpusHead" in result["report"] or "ID HEADER" in result["report"]


class TestAudioMetadata:
    def test_audio_metadata_plugin_on_wav(self, sample_wav, tmp_path):
        from core.plugins.audio_metadata_plugin import AudioMetadataPlugin

        plugin = AudioMetadataPlugin()
        assert plugin.name == "audio_metadata"
        assert "audio" in plugin.supported_types
        result = plugin.analyze(sample_wav, {"_job_staging_dir": str(tmp_path / "meta")})
        assert result["success"] is True
        assert "summary" in result
        assert "metadata" in result
        assert os.path.exists(result["metadata_json_path"])
        assert os.path.exists(result["metadata_report_path"])
        assert result["summary"]["codec"] or result["probe"]

    def test_classify_id3_family(self):
        from core.metadata.audio_extractor import _classify_audio_tag

        assert _classify_audio_tag("ID3v2:Title") == "id3"
        assert _classify_audio_tag("Vorbis:Encoder") == "vorbis"
        assert _classify_audio_tag("RIFF:Comment") == "riff"
        assert _classify_audio_tag("QuickTime:CreateDate") == "quicktime"
        assert _classify_audio_tag("XMP:CreatorTool") == "xmp"
        assert _classify_audio_tag("C2PA:ClaimGenerator") == "c2pa"
        assert _classify_audio_tag("JUMBF:JUMDLabel") == "c2pa"

    def test_audio_metadata_includes_c2pa_probe(self, sample_wav, tmp_path):
        from core.plugins.audio_metadata_plugin import AudioMetadataPlugin

        plugin = AudioMetadataPlugin()
        result = plugin.analyze(sample_wav, {"_job_staging_dir": str(tmp_path / "meta_c2pa")})
        assert result["success"] is True
        assert "c2pa_structured" in result
        assert "c2pa" in result["metadata"]["families"]
        # WAV comum: motor disponivel, manifesto ausente
        if result["c2pa_structured"].get("available"):
            assert result["c2pa_structured"]["present"] is False
            assert "c2pa-python" in (result["summary"].get("metadata_engines") or [])


class TestAudioPluginsList:
    def test_all_audio_plugins_registered(self):
        from core.plugin_registry import PluginRegistry

        registry = PluginRegistry()
        from pathlib import Path

        plugins_dir = Path(__file__).resolve().parents[2] / "src" / "backend" / "core" / "plugins"
        registry.discover_and_register(str(plugins_dir))
        assert "mp3_parser" in registry.PLUGINS
        assert "opus_parser" in registry.PLUGINS
        assert "audio_metadata" in registry.PLUGINS
        assert "audio_enf" in registry.PLUGINS
        assert "audio_spoofing_detection" in registry.PLUGINS


class TestAudioSpoofingDetection:
    def test_detector_catalog_has_bibliography_and_repo(self):
        from forensics.audio_spoofing.runtime import (
            AUDIO_SPOOFING_ANALYSIS_DF_ARENA,
            AUDIO_SPOOFING_ANALYSIS_SLS_XLSR,
            AUDIO_SPOOFING_ANALYSIS_TFCL,
            AUDIO_SPOOFING_ANALYSIS_WEDEFENSE,
            DETECTOR_CATALOG,
        )

        by_id = {row["id"]: row for row in DETECTOR_CATALOG}
        assert set(by_id) == {
            AUDIO_SPOOFING_ANALYSIS_DF_ARENA,
            AUDIO_SPOOFING_ANALYSIS_SLS_XLSR,
            AUDIO_SPOOFING_ANALYSIS_WEDEFENSE,
            AUDIO_SPOOFING_ANALYSIS_TFCL,
        }
        for row in DETECTOR_CATALOG:
            assert row["label"]
            assert row["description"]
            assert row["paper_title"]
            assert row["paper_url"].startswith("http")
            assert row["repo_url"].startswith("http")
        assert "2601.15240" in by_id[AUDIO_SPOOFING_ANALYSIS_WEDEFENSE]["paper_url"]
        assert "huggingface.co" in by_id[AUDIO_SPOOFING_ANALYSIS_WEDEFENSE]["repo_url"]
        assert "QiShanZhang/SLSforASVspoof-2021-DF" in by_id[AUDIO_SPOOFING_ANALYSIS_SLS_XLSR]["repo_url"]
        assert "JunXue" in by_id[AUDIO_SPOOFING_ANALYSIS_TFCL]["repo_url"]

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

        def fake_run(audio, sr, window_seconds=4.0, selected_analyses=None, on_progress=None, **kwargs):
            calls.append(len(audio))
            return {
                "individual_results": [["DF Arena 1B", "0.1000", "-0.1000", "-0.09", "Spoof", "cpu"]],
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
        from forensics.audio_spoofing import runtime as spoof_runtime

        monkeypatch.setattr(spoof_runtime, "runtime_status", lambda: (True, ""))
        monkeypatch.setattr(
            spoof_runtime,
            "detector_runtime_status",
            lambda detector_id: (
                (True, "")
                if detector_id in {"df_arena_1b", "sls_xlsr", "wedefense_wavlm_mhfa", "tfcl_xlsr"}
                else (False, "x")
            ),
        )
        plugin = adapter_mod.AudioSpoofingAdapter()
        ok, _ = plugin.validate_parameters({
            "selected_analyses": ["df_arena_1b", "sls_xlsr", "wedefense_wavlm_mhfa", "tfcl_xlsr"],
        })
        assert ok is True
        ok, msg = plugin.validate_parameters({"selected_analyses": []})
        assert ok is False
        ok, msg = plugin.validate_parameters({"selected_analyses": ["nao_existe"]})
        assert ok is False
        assert "invalidos" in msg.lower()

    def test_validate_use_augmented_reference(self, monkeypatch):
        from core.plugins import audio_spoofing_adapter as adapter_mod

        monkeypatch.setattr(adapter_mod, "runtime_status", lambda: (True, ""))
        plugin = adapter_mod.AudioSpoofingAdapter()

        ok, msg = plugin.validate_parameters({"use_augmented_reference": False})
        assert ok is True
        assert msg == ""

        ok, msg = plugin.validate_parameters({"use_augmented_reference": "yes"})
        assert ok is False
        assert "booleano" in msg

    def test_validate_reference_augmentations(self, monkeypatch):
        from core.plugins import audio_spoofing_adapter as adapter_mod

        monkeypatch.setattr(adapter_mod, "runtime_status", lambda: (True, ""))
        monkeypatch.setattr(adapter_mod, "representations_matrix_available", lambda _path: True)
        plugin = adapter_mod.AudioSpoofingAdapter()

        ok, msg = plugin.validate_parameters({"reference_augmentations": ["mp3_128k"]})
        assert ok is True
        assert msg == ""

        ok, msg = plugin.validate_parameters({"reference_augmentations": "mp3_128k"})
        assert ok is False
        assert "lista" in msg.lower()

        ok, msg = plugin.validate_parameters({"reference_augmentations": ["nao_existe"]})
        assert ok is False
        assert "invalidas" in msg.lower()

    def test_validate_use_latent_typicality(self, monkeypatch):
        from core.plugins import audio_spoofing_adapter as adapter_mod

        monkeypatch.setattr(adapter_mod, "runtime_status", lambda: (True, ""))
        monkeypatch.setattr(adapter_mod, "representations_matrix_available", lambda _path: False)
        plugin = adapter_mod.AudioSpoofingAdapter()

        ok, msg = plugin.validate_parameters({"use_latent_typicality": False})
        assert ok is True

        ok, msg = plugin.validate_parameters({"use_latent_typicality": "yes"})
        assert ok is False
        assert "booleano" in msg

        ok, msg = plugin.validate_parameters({"use_latent_typicality": True})
        assert ok is False
        assert "representacoes" in msg.lower()

        monkeypatch.setattr(adapter_mod, "representations_matrix_available", lambda _path: True)
        ok, msg = plugin.validate_parameters({"use_latent_typicality": True})
        assert ok is True

    def test_validate_augmented_reference_with_representations_matrix(self, monkeypatch):
        from core.plugins import audio_spoofing_adapter as adapter_mod

        monkeypatch.setattr(adapter_mod, "runtime_status", lambda: (True, ""))
        monkeypatch.setattr(adapter_mod, "representations_matrix_available", lambda _path: True)
        plugin = adapter_mod.AudioSpoofingAdapter()
        ok, msg = plugin.validate_parameters({"use_augmented_reference": True})
        assert ok is True
        assert msg == ""

    def test_use_latent_typicality_passes_flag_and_embeddings(self, sample_wav, monkeypatch):
        from core.plugins import audio_spoofing_adapter as adapter_mod

        monkeypatch.setattr(adapter_mod, "runtime_status", lambda: (True, ""))
        monkeypatch.setattr(adapter_mod, "representations_matrix_available", lambda _path: True)

        run_calls: list[dict] = []

        def fake_run(audio, sr, window_seconds=4.0, selected_analyses=None, on_progress=None, return_embedding=False):
            run_calls.append({"return_embedding": return_embedding})
            return {
                "individual_results": [["DF Arena 1B", "0.1000", "-0.1000", "-0.09", "Spoof", "cpu"]],
                "detector_scores": {
                    "df_arena_1b": {
                        "spoof_prob": 0.5,
                        "bonafide_prob": 0.5,
                        "bonafide_logit": 0.0,
                        "label": "uncertain",
                        "embedding": [0.1, 0.2],
                    },
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

        monkeypatch.setattr(adapter_mod, "run_audio_spoofing_analysis", fake_run)

        lr_calls: list[dict] = []

        def fake_compute_reference_lr(**kwargs):
            lr_calls.append(kwargs)
            return {
                "artifact_filenames": {
                    "tippett": "lr_reference_tippett.png",
                    "distribution": "lr_reference_distribution.png",
                    "identity": "lr_reference_identity.png",
                    "summary": "lr_reference_summary.txt",
                },
                "latent_typicality": True,
            }

        monkeypatch.setattr(adapter_mod, "compute_reference_lr", fake_compute_reference_lr)

        plugin = adapter_mod.AudioSpoofingAdapter()
        result = plugin.analyze(
            sample_wav,
            {
                "reference_lr_enabled": True,
                "use_latent_typicality": True,
                "reference_population": {"items": []},
                "selected_analyses": ["df_arena_1b"],
            },
        )

        assert result["success"] is True
        assert len(run_calls) == 1
        assert run_calls[0]["return_embedding"] is True
        assert len(lr_calls) == 1
        assert lr_calls[0]["use_latent_typicality"] is True

    def test_analyze_passes_selected_augmentations(self, sample_wav, monkeypatch):
        from core.plugins import audio_spoofing_adapter as adapter_mod

        monkeypatch.setattr(adapter_mod, "runtime_status", lambda: (True, ""))
        monkeypatch.setattr(adapter_mod, "representations_matrix_available", lambda _path: True)

        def fake_run(audio, sr, window_seconds=4.0, selected_analyses=None, on_progress=None, return_embedding=False):
            return {
                "individual_results": [["DF Arena 1B", "0.1000", "-0.1000", "-0.09", "Spoof", "cpu"]],
                "detector_scores": {
                    "df_arena_1b": {
                        "spoof_prob": 0.5,
                        "bonafide_prob": 0.5,
                        "bonafide_logit": 0.0,
                        "label": "uncertain",
                    },
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

        monkeypatch.setattr(adapter_mod, "run_audio_spoofing_analysis", fake_run)
        lr_calls: list[dict] = []

        def fake_compute_reference_lr(**kwargs):
            lr_calls.append(kwargs)
            return {
                "artifact_filenames": {
                    "tippett": "lr_reference_tippett.png",
                    "distribution": "lr_reference_distribution.png",
                    "identity": "lr_reference_identity.png",
                    "summary": "lr_reference_summary.txt",
                }
            }

        monkeypatch.setattr(adapter_mod, "compute_reference_lr", fake_compute_reference_lr)
        plugin = adapter_mod.AudioSpoofingAdapter()
        result = plugin.analyze(
            sample_wav,
            {
                "reference_lr_enabled": True,
                "reference_augmentations": ["opus_32k", "mp3_128k"],
                "use_augmented_reference": True,
                "reference_population": {"items": []},
                "selected_analyses": ["df_arena_1b"],
            },
        )
        assert result["success"] is True
        assert lr_calls[0]["selected_augmentations"] == ("mp3_128k", "opus_32k")
        assert lr_calls[0]["sample_multiplier"] == 3

    def test_adapter_multi_detector_mock(self, sample_wav, monkeypatch):
        from core.plugins import audio_spoofing_adapter as adapter_mod

        def fake_run(audio, sr, window_seconds=4.0, selected_analyses=None, on_progress=None, **kwargs):
            return {
                "individual_results": [
                    ["DF Arena 1B", "0.7000", "-0.3000", "-0.43", "Spoof", "cpu"],
                    ["SLS XLS-R (ACM MM 2024)", "-0.4000", "0.2000", "0.26", "Bonafide", "cpu"],
                ],
                "detector_scores": {
                    "df_arena_1b": {"spoof_prob": 0.7, "bonafide_prob": 0.3, "bonafide_logit": -0.3, "label": "spoof"},
                    "sls_xlsr": {"spoof_prob": 0.4, "bonafide_prob": 0.6, "bonafide_logit": 0.2, "label": "bonafide"},
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
        from forensics.wedefense_spoofing.wedefense_pipeline import _wedefense_probs_to_scores
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
        import forensics.sls_spoofing.sls_runtime as sls_runtime

        repo = Path(__file__).resolve().parents[2]
        backend_cwd = repo / "src" / "backend"
        # Settings resolve relative MODELS_DIR against repo root (not CWD).
        monkeypatch.chdir(backend_cwd)
        monkeypatch.setenv("MODELS_DIR", str(repo / "models"))
        get_settings.cache_clear()

        models_dir = sls_runtime._models_dir()
        workspace = sls_runtime._workspace_root()
        assert models_dir == (workspace / "models" / "sls_spoofing").resolve()
        get_settings.cache_clear()


class TestDFArenaAggregation:
    def test_label_spoof_when_bonafide_logit_negative(self):
        from forensics.audio_spoofing.pipeline import classification_from_bonafide_logit

        assert classification_from_bonafide_logit(-0.1) == "Spoof"
        assert classification_from_bonafide_logit(-1.0) == "Spoof"

    def test_label_bonafide_when_bonafide_logit_nonnegative(self):
        from forensics.audio_spoofing.pipeline import classification_from_bonafide_logit

        assert classification_from_bonafide_logit(0.0) == "Bonafide"
        assert classification_from_bonafide_logit(2.0) == "Bonafide"
