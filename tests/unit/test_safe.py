"""Unit tests for SAFE synthetic image detection adapter."""

from __future__ import annotations


class TestSafeAdapter:
    def test_safe_row_format(self):
        from core.legacy.effort.effort_pipeline import effort_row

        row = effort_row("SAFE (KDD'25)", 0.73, inference_device="cuda")
        assert len(row) == 6
        assert row[0] == "SAFE (KDD'25)"
        assert row[1] == "0.7300"
        assert row[4] in ("AI", "REAL", "Incerto")

    def test_predict_safe_row_returns_none_when_weights_missing(self, monkeypatch):
        from core.legacy.safe.safe_pipeline import predict_safe_row
        from PIL import Image

        monkeypatch.setattr(
            "core.legacy.safe.safe_pipeline.safe_runtime_status",
            lambda: (False, "pesos ausentes"),
        )
        assert predict_safe_row(Image.new("RGB", (64, 64))) is None

    def test_warm_safe_skips_missing_weights(self, monkeypatch):
        from core.legacy.safe.safe_pipeline import warm_safe_model

        monkeypatch.setattr(
            "core.legacy.safe.safe_pipeline.safe_runtime_status",
            lambda: (False, "pesos ausentes"),
        )
        assert warm_safe_model() is False
