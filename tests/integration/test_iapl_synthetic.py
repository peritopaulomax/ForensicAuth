"""Integration: IAPL rows in synthetic image detection table."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

WORKSPACE = Path(__file__).resolve().parents[2]
AUTHENTIC = WORKSPACE / "uploads-dev" / "7bab0877-d873-4b68-aad9-de2e79ca14e7.jpg"


@pytest.mark.integration
class TestIaplInSyntheticDetectionTable:
    def test_ensemble_includes_iapl_rows_when_ready(self):
        from core.legacy.iapl.iapl_runtime import any_iapl_ready
        from core.legacy.synthetic_image_detection.pipeline import predict_ensemble
        from core.legacy.synthetic_image_detection.runtime import runtime_status

        ok_runtime, reason = runtime_status()
        if not ok_runtime:
            pytest.skip(reason)

        ok_iapl, _ = any_iapl_ready()
        if not ok_iapl:
            pytest.skip("Pesos IAPL ausentes")

        if not AUTHENTIC.is_file():
            pytest.skip("example_input ausente")

        image = Image.open(AUTHENTIC).convert("RGB")
        rows = predict_ensemble(image)
        iapl_rows = [r for r in rows if r[0].startswith("IAPL (")]
        assert len(iapl_rows) >= 1
        for row in iapl_rows:
            assert len(row) == 6
            p = float(row[1])
            assert 0.0 <= p <= 1.0
            assert row[4] in ("AI", "REAL", "Incerto")
            assert row[5] in ("GPU", "CPU")
