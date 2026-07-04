"""Integration: CLIDE row in synthetic image detection table."""

from __future__ import annotations

import pytest
from PIL import Image


@pytest.mark.integration
class TestClideSyntheticDetectionTable:
    def test_clide_row_when_ready(self, monkeypatch):
        import torch

        monkeypatch.setattr(
            "core.legacy.clide.clide_pipeline.resolve_inference_device",
            lambda: torch.device("cpu"),
        )
        from core.legacy.clide.clide_pipeline import predict_clide_row
        from core.legacy.clide.clide_runtime import any_clide_ready

        ok, reason = any_clide_ready()
        if not ok:
            pytest.skip(reason)

        image = Image.new("RGB", (224, 224), color=(96, 128, 160))
        row = predict_clide_row(image)

        assert row is not None
        assert len(row) == 6
        assert row[0] == "CLIDE (local likelihood)"
        assert float(row[1]) < 0.0
        assert row[2] == "N/A"
        assert row[3].startswith("||z||²=")
        assert row[4] == "Sem limiar"
        assert row[5] in ("GPU", "CPU")
