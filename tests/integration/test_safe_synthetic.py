"""Integration: SAFE in synthetic image detection ensemble."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

WORKSPACE = Path(__file__).resolve().parents[2]
AUTHENTIC = WORKSPACE / "uploads-dev" / "7bab0877-d873-4b68-aad9-de2e79ca14e7.jpg"


@pytest.mark.integration
class TestSafeInSyntheticDetectionTable:
    def test_ensemble_includes_safe_row_when_selected(self):
        from core.legacy.safe.safe_runtime import safe_runtime_status
        from core.legacy.synthetic_image_detection.pipeline import (
            SYNTHETIC_ANALYSIS_SAFE,
            predict_ensemble,
        )
        from core.legacy.synthetic_image_detection.runtime import runtime_status

        ok_runtime, reason = runtime_status()
        if not ok_runtime:
            pytest.skip(reason)

        ok_safe, safe_reason = safe_runtime_status()
        if not ok_safe:
            pytest.skip(safe_reason)

        if not AUTHENTIC.is_file():
            pytest.skip("example_input ausente")

        image = Image.open(AUTHENTIC).convert("RGB")
        rows = predict_ensemble(image, selected_analyses=[SYNTHETIC_ANALYSIS_SAFE])
        safe_rows = [r for r in rows if r[0].startswith("SAFE")]
        assert len(safe_rows) == 1

    def test_ensemble_omits_safe_when_not_selected(self):
        from core.legacy.synthetic_image_detection.pipeline import predict_ensemble
        from core.legacy.synthetic_image_detection.runtime import runtime_status

        ok_runtime, reason = runtime_status()
        if not ok_runtime:
            pytest.skip(reason)

        if not AUTHENTIC.is_file():
            pytest.skip("example_input ausente")

        image = Image.open(AUTHENTIC).convert("RGB")
        rows = predict_ensemble(
            image,
            selected_analyses=[
                "ai_image_detector_deploy",
                "sdxl_flux_detector_v1_1",
                "bfree",
                "corvi2023",
            ],
        )
        safe_rows = [r for r in rows if r[0].startswith("SAFE")]
        assert safe_rows == []
