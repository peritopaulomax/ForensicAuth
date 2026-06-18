"""Unit tests for CAMO (BitMind) synthetic image detection adapter."""

from __future__ import annotations


class TestCamoAdapter:
    def test_camo_row_format(self):
        from core.legacy.camo.camo_runtime import MODEL_LABEL
        from core.legacy.effort.effort_pipeline import effort_row

        row = effort_row(MODEL_LABEL, 0.61, inference_device="cuda")
        assert len(row) == 6
        assert row[0] == MODEL_LABEL
        assert row[1] == "0.6100"
        assert row[4] in ("AI", "REAL", "Incerto")

    def test_predict_camo_row_returns_none_when_unavailable(self, monkeypatch):
        from core.legacy.camo.camo_pipeline import predict_camo_row
        from PIL import Image

        monkeypatch.setattr(
            "core.legacy.camo.camo_pipeline.camo_runtime_status",
            lambda: (False, "pesos ausentes"),
        )
        assert predict_camo_row(Image.new("RGB", (64, 64))) is None

    def test_warm_camo_skips_missing_weights(self, monkeypatch):
        from core.legacy.camo.camo_pipeline import warm_camo_model

        monkeypatch.setattr(
            "core.legacy.camo.camo_pipeline.camo_runtime_status",
            lambda: (False, "pesos ausentes"),
        )
        assert warm_camo_model() is False

    def test_predict_camo_row_with_mocked_inference(self, monkeypatch):
        import torch
        from PIL import Image

        from core.legacy.camo.camo_pipeline import predict_camo_row
        from core.legacy.camo.camo_runtime import MODEL_LABEL

        monkeypatch.setattr(
            "core.legacy.camo.camo_pipeline.camo_runtime_status",
            lambda: (True, ""),
        )
        monkeypatch.setattr(
            "core.legacy.camo.camo_pipeline.run_with_device_fallback",
            lambda fn, **_: (fn(torch.device("cpu")), torch.device("cpu")),
        )
        monkeypatch.setattr(
            "core.legacy.camo.camo_pipeline.infer_camo_from_pil",
            lambda *_a, **_k: 0.82,
        )

        row = predict_camo_row(Image.new("RGB", (128, 128)))
        assert row is not None
        assert row[0] == MODEL_LABEL
        assert row[1] == "0.8200"
        assert row[5] == "CPU"
