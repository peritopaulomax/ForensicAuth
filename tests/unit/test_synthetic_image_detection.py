"""Unit tests for synthetic image detection ensemble."""

from pathlib import Path

import pytest


class TestSyntheticImageDetectionRuntime:
    def test_resolve_models_dir(self):
        from core.legacy.synthetic_image_detection.runtime import resolve_models_dir

        root = Path(__file__).resolve().parents[2]
        candidates = [
            root / "models" / "synthetic_image_detection",
            root / "models" / "sepael",
            root / "Legados" / "imagens" / "Gradio-Deep-Sepael",
        ]
        expected = next(
            (
                d.resolve()
                for d in candidates
                if d.is_dir() and (d / "model1_xgboost_1p_20250809_213811.json").is_file()
            ),
            None,
        )
        if expected is None:
            pytest.skip("Pesos do ensemble ausentes neste ambiente")
        assert resolve_models_dir() == expected

    def test_runtime_status_reports_missing_deps_or_ok(self):
        from core.legacy.synthetic_image_detection.runtime import runtime_status

        ok, reason = runtime_status()
        if ok:
            assert reason == ""
        else:
            assert reason

    def test_huggingface_cache_ignores_incomplete_env_cache(self, monkeypatch, tmp_path):
        from app.config import get_settings
        from core.legacy.synthetic_image_detection.runtime import (
            HF_MODEL_IDS,
            _hf_cache_folder,
            huggingface_cache_dir,
        )

        models_dir = tmp_path / "models"
        expected = models_dir / "synthetic_image_detection" / "huggingface"
        for model_id in HF_MODEL_IDS:
            (expected / _hf_cache_folder(model_id)).mkdir(parents=True)
        incomplete = tmp_path / "deeclip" / "huggingface"
        incomplete.mkdir(parents=True)

        monkeypatch.setenv("MODELS_DIR", str(models_dir))
        monkeypatch.setenv("HF_HUB_CACHE", str(incomplete))
        get_settings.cache_clear()

        assert huggingface_cache_dir() == expected.resolve()

    def test_plugin_registered(self):
        from core.plugin_registry import PluginRegistry
        from core.technique_ids import SYNTHETIC_IMAGE_DETECTION

        registry = PluginRegistry()
        plugins_dir = Path(__file__).resolve().parents[2] / "src" / "backend" / "core" / "plugins"
        registry.discover_and_register(str(plugins_dir))
        assert SYNTHETIC_IMAGE_DETECTION in registry.PLUGINS

    def test_validate_parameters_mode(self, monkeypatch):
        from core.plugins.synthetic_image_detection_adapter import SyntheticImageDetectionAdapter

        monkeypatch.setattr(
            "core.plugins.synthetic_image_detection_adapter.runtime_status",
            lambda: (True, ""),
        )
        plugin = SyntheticImageDetectionAdapter()
        ok, msg = plugin.validate_parameters({"mode": "invalid"})
        assert ok is False
        assert "mode" in msg

    def test_validate_selected_analyses(self, monkeypatch):
        from core.plugins.synthetic_image_detection_adapter import SyntheticImageDetectionAdapter

        monkeypatch.setattr(
            "core.plugins.synthetic_image_detection_adapter.runtime_status",
            lambda: (True, ""),
        )
        plugin = SyntheticImageDetectionAdapter()

        ok, msg = plugin.validate_parameters(
            {
                "selected_analyses": [
                    "ai_image_detector_deploy",
                    "sdxl_flux_detector_v1_1",
                    "bfree",
                    "corvi2023",
                ]
            }
        )
        assert ok is True
        assert msg == ""

        ok, msg = plugin.validate_parameters({"selected_analyses": []})
        assert ok is False
        assert "pelo menos uma" in msg

        ok, msg = plugin.validate_parameters({"selected_analyses": ["nao_existe"]})
        assert ok is False
        assert "invalidas" in msg

    def test_validate_use_augmented_reference(self, monkeypatch):
        from core.plugins.synthetic_image_detection_adapter import SyntheticImageDetectionAdapter

        monkeypatch.setattr(
            "core.plugins.synthetic_image_detection_adapter.runtime_status",
            lambda: (True, ""),
        )
        plugin = SyntheticImageDetectionAdapter()

        ok, msg = plugin.validate_parameters({"use_augmented_reference": False})
        assert ok is True
        assert msg == ""

        ok, msg = plugin.validate_parameters({"use_augmented_reference": "yes"})
        assert ok is False
        assert "booleano" in msg

    def test_use_augmented_reference_uses_augmented_score_matrix(self, monkeypatch):
        from core.plugins import synthetic_image_detection_adapter as adapter_module
        from core.plugins.synthetic_image_detection_adapter import SyntheticImageDetectionAdapter

        monkeypatch.setattr(
            "core.plugins.synthetic_image_detection_adapter.runtime_status",
            lambda: (True, ""),
        )

        from PIL import Image

        def fake_run_analysis(*args, **kwargs):
            return {
                "individual_results": [
                    {
                        "analyzer": "ai_image_detector_deploy",
                        "label": "AI",
                        "score": 0.9,
                        "fake_prob": 0.9,
                        "real_prob": 0.1,
                    }
                ],
                "detector_scores": {
                    "ai_image_detector_deploy": {"fake_prob": 0.9},
                    "sdxl_flux_detector_v1_1": {"fake_prob": 0.1},
                    "bfree": {"fake_prob": 0.2},
                    "corvi2023": {"fake_prob": 0.3},
                    "safe": {"fake_prob": 0.4},
                },
                "generate_visuals": True,
                "selected_analyses": ["ai_image_detector_deploy"],
                "inference_device": "cpu",
                "input_image": Image.new("RGB", (64, 64), color="red"),
                "input_fft": Image.new("RGB", (64, 64), color="blue"),
                "nlm_residue": None,
                "median_residue": None,
                "nlm_fft": None,
                "median_fft": None,
            }

        monkeypatch.setattr(
            adapter_module,
            "run_synthetic_image_detection_analysis",
            fake_run_analysis,
        )

        calls = []

        def fake_compute_reference_lr(*, score_matrix, sample_multiplier, **kwargs):
            calls.append({"score_matrix": score_matrix, "sample_multiplier": sample_multiplier})
            return {
                "artifact_filenames": {
                    "tippett": "lr_reference_tippett.png",
                    "distribution": "lr_reference_distribution.png",
                    "identity": "lr_reference_identity.png",
                    "summary": "lr_reference_summary.txt",
                }
            }

        monkeypatch.setattr(adapter_module, "compute_reference_lr", fake_compute_reference_lr)

        plugin = SyntheticImageDetectionAdapter()
        from PIL import Image
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            img_path = Path(tmp) / "dummy.png"
            Image.new("RGB", (64, 64), color="red").save(img_path)
            result = plugin.analyze(
                str(img_path),
                {
                    "reference_lr_enabled": True,
                    "use_augmented_reference": True,
                    "reference_population": {"items": []},
                    "selected_analyses": ["ai_image_detector_deploy"],
                    "job_id": "test-job",
                    "evidence_id": "test-evidence",
                    "case_id": "test-case",
                    "result_dir": tmp,
                },
            )

        assert result["success"] is True
        assert len(calls) == 1
        assert calls[0]["score_matrix"] == adapter_module._AUGMENTED_SCORE_MATRIX
        assert calls[0]["sample_multiplier"] == 5


class TestSyntheticImageDetectionModel4:
    def test_as_rgb_converts_rgba(self):
        from PIL import Image

        from core.legacy.synthetic_image_detection.pipeline import _as_rgb

        rgba = Image.new("RGBA", (64, 64), (10, 20, 30, 200))
        rgb = _as_rgb(rgba)
        assert rgb.mode == "RGB"
        assert rgb.size == (64, 64)

    def test_predict_includes_sdxl_for_rgba_image(self, monkeypatch):
        from PIL import Image

        from app.config import get_settings
        from core.legacy.synthetic_image_detection import pipeline as sp
        from core.legacy.synthetic_image_detection.runtime import runtime_status

        root = Path(__file__).resolve().parents[2]
        models_dir = root / "models"
        weight_dirs = [models_dir / "synthetic_image_detection", models_dir / "sepael"]
        hf_cache = next(
            (d / "huggingface" for d in weight_dirs if (d / "huggingface").is_dir()),
            None,
        )
        weights_dir = next(
            (d for d in weight_dirs if (d / "model1_xgboost_1p_20250809_213811.json").is_file()),
            None,
        )
        if weights_dir is None:
            pytest.skip("Pesos do ensemble ausentes neste ambiente")
        if hf_cache is None:
            pytest.skip("Cache HuggingFace ausente")

        monkeypatch.setenv("MODELS_DIR", str(models_dir))
        monkeypatch.setenv("HF_HUB_CACHE", str(hf_cache))
        monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
        get_settings.cache_clear()

        ok, reason = runtime_status()
        if not ok:
            pytest.skip(reason or "Detecção de imagens sintéticas indisponivel")

        sp._DETECTION_MODELS = None
        sp._MODEL1_XGB = None
        sp._FFT_EXTRACTOR = None
        sp._LOAD_ERROR = None

        img = Image.new("RGBA", (320, 240), (120, 80, 200, 255))
        results = sp.predict_ensemble(img)
        names = [row[0] for row in results]

        assert "sdxl-flux-detector_v1.1" in names
        assert "ai-image-detector-deploy" in names
        optional_names = [
            n
            for n in names
            if n.startswith(
                (
                    "B-Free",
                    "On the detection of synthetic images generated by diffusion models.",
                    "SAFE",
                )
            )
        ]
        assert len(names) == 2 + len(optional_names)

    def test_predict_ensemble_respects_selected_bfree_analysis(self, monkeypatch):
        from PIL import Image

        from core.legacy.synthetic_image_detection import pipeline as sp

        def fail_if_base_models_load(*args, **kwargs):
            raise AssertionError("base models should not load when only B-Free is selected")

        monkeypatch.setattr(sp, "_ensure_models_loaded", fail_if_base_models_load)
        monkeypatch.setattr(
            "core.legacy.bfree.bfree_pipeline.predict_bfree_row",
            lambda image, on_progress=None: [
                "B-Free (Bias-free synthetic image detector)",
                "0.9000",
                "0.1000",
                "score=2.0000",
                "AI",
                "CPU",
            ],
        )

        img = Image.new("RGB", (64, 64), (10, 20, 30))
        rows = sp.predict_ensemble(img, selected_analyses=["bfree"])

        assert rows == [
            [
                "B-Free (Bias-free synthetic image detector)",
                "0.9000",
                "0.1000",
                "score=2.0000",
                "AI",
                "CPU",
            ]
        ]

    def test_predict_ensemble_runs_selected_bfree_and_corvi_without_base_models(self, monkeypatch):
        from PIL import Image

        from core.legacy.synthetic_image_detection import pipeline as sp

        def fail_if_base_models_load(*args, **kwargs):
            raise AssertionError("base models should not load when only B-Free/Corvi are selected")

        monkeypatch.setattr(sp, "_ensure_models_loaded", fail_if_base_models_load)
        monkeypatch.setattr(
            "core.legacy.bfree.bfree_pipeline.predict_bfree_row",
            lambda image, on_progress=None: [
                "B-Free (Bias-free synthetic image detector)",
                "0.8000",
                "0.2000",
                "score=1.3863",
                "AI",
                "CPU",
            ],
        )
        monkeypatch.setattr(
            "core.legacy.truebees_clip_d.clipd_pipeline.predict_corvi2023_row",
            lambda image, on_progress=None: [
                "On the detection of synthetic images generated by diffusion models. (Corvi2023)",
                "0.2000",
                "0.8000",
                "LLR=-1.3863; repo=github.com/grip-unina/DMimageDetection",
                "REAL",
                "CPU",
            ],
        )

        img = Image.new("RGB", (64, 64), (10, 20, 30))
        rows = sp.predict_ensemble(
            img,
            selected_analyses=["bfree", "corvi2023"],
        )

        assert [row[0] for row in rows] == [
            "B-Free (Bias-free synthetic image detector)",
            "On the detection of synthetic images generated by diffusion models. (Corvi2023)",
        ]
