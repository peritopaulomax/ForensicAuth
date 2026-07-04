"""Integration: Effort removed from synthetic image detection table."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

WORKSPACE = Path(__file__).resolve().parents[2]
AUTHENTIC = WORKSPACE / "uploads-dev" / "7bab0877-d873-4b68-aad9-de2e79ca14e7.jpg"


@pytest.mark.integration
class TestEffortInSyntheticDetectionTable:
    def test_ensemble_excludes_effort_rows(self):
        from core.legacy.synthetic_image_detection.pipeline import predict_ensemble
        from core.legacy.synthetic_image_detection.runtime import runtime_status

        ok_runtime, reason = runtime_status()
        if not ok_runtime:
            pytest.skip(reason)

        if not AUTHENTIC.is_file():
            pytest.skip("example_input ausente")

        image = Image.open(AUTHENTIC).convert("RGB")
        rows = predict_ensemble(image)
        effort_rows = [r for r in rows if r[0].startswith("Effort (")]
        assert effort_rows == []

    @pytest.mark.skipif(not AUTHENTIC.is_file(), reason="example_input ausente")
    def test_run_analysis_excludes_effort_in_individual_results(self):
        from core.legacy.synthetic_image_detection.pipeline import run_synthetic_image_detection_analysis
        from core.legacy.synthetic_image_detection.runtime import runtime_status

        ok_runtime, reason = runtime_status()
        if not ok_runtime:
            pytest.skip(reason)

        image = Image.open(AUTHENTIC).convert("RGB")
        out = run_synthetic_image_detection_analysis(image, generate_visuals=False)
        names = [r[0] for r in out["individual_results"]]
        assert not any("GenImage" in n for n in names)
        assert not any("Chameleon" in n for n in names)
