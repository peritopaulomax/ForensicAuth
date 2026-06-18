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
        assert "model1_xgb (FFT)" in names
        effort_names = [n for n in names if n.startswith("Effort (")]
        optional_names = [n for n in names if n.startswith(("SAFE", "IAPL", "CAMO"))]
        assert len(names) == 3 + len(effort_names) + len(optional_names)
        for en in effort_names:
            assert "GenImage" in en or "Chameleon" in en
