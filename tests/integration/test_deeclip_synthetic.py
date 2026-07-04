"""Integration: DeeCLIP row in synthetic image detection table."""

from __future__ import annotations

import pytest
from PIL import Image


@pytest.mark.integration
class TestDeeclipSyntheticDetectionTable:
    def test_ensemble_includes_deeclip_row_when_ready(self):
        from core.legacy.deeclip.deeclip_runtime import any_deeclip_ready
        from core.legacy.deeclip.deeclip_pipeline import predict_deeclip_row

        ok_deeclip, reason = any_deeclip_ready()
        if not ok_deeclip:
            pytest.skip(reason)

        image = Image.new("RGB", (224, 224), color=(96, 128, 160))
        row = predict_deeclip_row(image)

        assert row is not None
        assert len(row) == 6
        p = float(row[1])
        assert 0.0 <= p <= 1.0
        assert row[4] in ("AI", "REAL", "Incerto")
        assert row[5] in ("GPU", "CPU")
