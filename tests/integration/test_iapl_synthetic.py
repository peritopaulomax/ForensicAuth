"""Integration: IAPL removed from synthetic image detection table."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

WORKSPACE = Path(__file__).resolve().parents[2]
AUTHENTIC = WORKSPACE / "uploads-dev" / "7bab0877-d873-4b68-aad9-de2e79ca14e7.jpg"


@pytest.mark.integration
class TestIaplInSyntheticDetectionTable:
    def test_ensemble_excludes_iapl_rows(self):
        from core.legacy.synthetic_image_detection.pipeline import predict_ensemble
        from core.legacy.synthetic_image_detection.runtime import runtime_status

        ok_runtime, reason = runtime_status()
        if not ok_runtime:
            pytest.skip(reason)

        if not AUTHENTIC.is_file():
            pytest.skip("example_input ausente")

        image = Image.open(AUTHENTIC).convert("RGB")
        rows = predict_ensemble(image)
        iapl_rows = [r for r in rows if r[0].startswith("IAPL (")]
        assert iapl_rows == []
