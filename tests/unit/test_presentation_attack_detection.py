"""Unit tests for Presentation Attack Detection (PAD) plugin."""

from pathlib import Path

import cv2
import numpy as np
import pytest


class TestPresentationAttackDetectionRuntime:
    def test_runtime_status_reports_ok_when_weights_present(self):
        from core.legacy.pad.runtime import pad_runtime_status

        ok, reason = pad_runtime_status()
        if ok:
            assert reason == ""
        else:
            assert reason

    def test_plugin_registered(self):
        from core.plugin_registry import PluginRegistry
        from core.technique_ids import PRESENTATION_ATTACK_DETECTION

        registry = PluginRegistry()
        plugins_dir = Path(__file__).resolve().parents[2] / "src" / "backend" / "core" / "plugins"
        registry.discover_and_register(str(plugins_dir))
        assert PRESENTATION_ATTACK_DETECTION in registry.PLUGINS

    def test_validate_parameters_accepts_defaults(self, monkeypatch):
        from core.plugins.presentation_attack_detection_adapter import PresentationAttackDetectionAdapter

        monkeypatch.setattr(
            "core.plugins.presentation_attack_detection_adapter.pad_runtime_status",
            lambda: (True, ""),
        )
        plugin = PresentationAttackDetectionAdapter()
        ok, msg = plugin.validate_parameters({})
        assert ok is True
        assert msg == ""

    def test_validate_parameters_rejects_invalid_threshold(self, monkeypatch):
        from core.plugins.presentation_attack_detection_adapter import PresentationAttackDetectionAdapter

        monkeypatch.setattr(
            "core.plugins.presentation_attack_detection_adapter.pad_runtime_status",
            lambda: (True, ""),
        )
        plugin = PresentationAttackDetectionAdapter()

        ok, msg = plugin.validate_parameters({"threshold": 1.5})
        assert ok is False
        assert "threshold" in msg

        ok, msg = plugin.validate_parameters({"threshold": "abc"})
        assert ok is False


class TestPresentationAttackDetectionModel:
    def test_adapter_returns_no_face_for_blank_image(self, monkeypatch, tmp_path):
        from core.plugins.presentation_attack_detection_adapter import PresentationAttackDetectionAdapter

        monkeypatch.setattr(
            "core.plugins.presentation_attack_detection_adapter.pad_runtime_status",
            lambda: (True, ""),
        )

        plugin = PresentationAttackDetectionAdapter()
        img = np.full((480, 360, 3), 128, dtype=np.uint8)
        path = tmp_path / "noface.jpg"
        cv2.imwrite(str(path), img)

        result = plugin.analyze(str(path), {})
        assert result["success"] is False
        assert result["error"] == "NO_FACE_DETECTED"

    def test_regression_vs_original_algorithm(self, monkeypatch, tmp_path):
        """Adapter output must match the original test.py algorithm on a real face.

        This test downloads a sample face from the upstream repository when
        weights are available. It compares the raw model label and the raw
        confidence score (before threshold adjustment) with a direct execution
        of the vendored pipeline.
        """
        import urllib.request

        from core.legacy.pad.anti_spoof_predict import AntiSpoofPredict
        from core.legacy.pad.generate_patches import CropImage
        from core.legacy.pad.runtime import pad_runtime_status
        from core.legacy.pad.utility import parse_model_name
        from core.plugins.presentation_attack_detection_adapter import PresentationAttackDetectionAdapter

        ok, reason = pad_runtime_status()
        if not ok:
            pytest.skip(reason or "Pesos PAD ausentes")

        monkeypatch.setattr(
            "core.plugins.presentation_attack_detection_adapter.pad_runtime_status",
            lambda: (True, ""),
        )

        sample_url = "https://raw.githubusercontent.com/minivision-ai/Silent-Face-Anti-Spoofing/master/images/sample/image_F1.jpg"
        sample_path = tmp_path / "image_F1.jpg"
        try:
            urllib.request.urlretrieve(sample_url, sample_path)
        except Exception as exc:
            pytest.skip(f"Nao foi possivel baixar imagem de exemplo: {exc}")

        model_dir = Path("models/pad/anti_spoof_models").resolve()
        detection_model_dir = Path("models/pad/detection_model").resolve()

        # Reference execution mirroring the original test.py
        model_test = AntiSpoofPredict(0, str(detection_model_dir))
        image_cropper = CropImage()
        image = cv2.imread(str(sample_path))
        image_bbox = model_test.get_bbox(image)
        prediction = np.zeros((1, 3))
        for model_name in sorted(p.name for p in model_dir.glob("*.pth")):
            h_input, w_input, _model_type, scale = parse_model_name(model_name)
            param = {
                "org_img": image,
                "bbox": image_bbox,
                "scale": scale,
                "out_w": w_input,
                "out_h": h_input,
                "crop": scale is not None,
            }
            img = image_cropper.crop(**param)
            prediction += model_test.predict(img, str(model_dir / model_name))

        original_label_idx = int(np.argmax(prediction))
        original_value = float(prediction[0][original_label_idx] / 2)
        original_label = "real" if original_label_idx == 1 else "fake"

        # Adapter execution
        plugin = PresentationAttackDetectionAdapter()
        result = plugin.analyze(str(sample_path), {})

        assert result["success"] is True
        assert result["adapter"] == "presentation_attack_detection"
        assert result["raw_label"] == original_label
        assert result["score"] == pytest.approx(
            original_value if original_label == "real" else 1.0 - original_value, abs=1e-6
        )
        assert result["bbox"]["w"] > 0
        assert result["bbox"]["h"] > 0
