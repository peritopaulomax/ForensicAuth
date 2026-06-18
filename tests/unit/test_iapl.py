"""Unit tests for IAPL synthetic image detection adapter."""

from __future__ import annotations


class TestIaplAdapter:
    def test_iapl_row_format(self):
        from core.legacy.effort.effort_pipeline import effort_row

        row = effort_row("IAPL (GenImage (SD v1.4))", 0.61, inference_device="cuda")
        assert len(row) == 6
        assert row[0].startswith("IAPL (")
        assert row[1] == "0.6100"

    def test_predict_iapl_rows_empty_when_unavailable(self, monkeypatch):
        from core.legacy.iapl.iapl_pipeline import predict_iapl_rows
        from PIL import Image

        monkeypatch.setattr(
            "core.legacy.iapl.iapl_pipeline.iapl_runtime_status",
            lambda *, variant: (False, "pesos ausentes"),
        )
        assert predict_iapl_rows(Image.new("RGB", (64, 64))) == []

    def test_warm_iapl_skips_missing_weights(self, monkeypatch):
        from core.legacy.iapl.iapl_pipeline import warm_iapl_models

        monkeypatch.setattr(
            "core.legacy.iapl.iapl_pipeline.iapl_runtime_status",
            lambda *, variant: (False, "pesos ausentes"),
        )
        assert warm_iapl_models() == []
