"""E2E Effort via tabela de detecção de imagens sintéticas (GenImage + Chameleon)."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

WORKSPACE = Path(__file__).resolve().parents[2]
AUTHENTIC = WORKSPACE / "uploads-dev" / "7bab0877-d873-4b68-aad9-de2e79ca14e7.jpg"


@pytest.mark.integration
class TestEffortInSyntheticDetectionTable:
    def test_ensemble_includes_effort_rows_when_weights_ready(self):
        from core.legacy.effort.effort_runtime import any_effort_ready
        from core.legacy.synthetic_image_detection.pipeline import predict_ensemble
        from core.legacy.synthetic_image_detection.runtime import runtime_status

        ok_runtime, reason = runtime_status()
        if not ok_runtime:
            pytest.skip(reason)

        ok_effort, _ = any_effort_ready()
        if not ok_effort:
            pytest.skip("Pesos Effort ausentes")

        if not AUTHENTIC.is_file():
            pytest.skip("example_input ausente")

        image = Image.open(AUTHENTIC).convert("RGB")
        rows = predict_ensemble(image)
        effort_rows = [r for r in rows if r[0].startswith("Effort (")]
        assert len(effort_rows) == 2
        for row in effort_rows:
            assert len(row) == 6
            p = float(row[1])
            assert 0.0 <= p <= 1.0
            assert row[4] in ("AI", "REAL", "Incerto")
            assert row[5] in ("GPU", "CPU")

    @pytest.mark.skipif(not AUTHENTIC.is_file(), reason="example_input ausente")
    def test_run_analysis_carries_effort_in_individual_results(self):
        from core.legacy.effort.effort_runtime import any_effort_ready
        from core.legacy.synthetic_image_detection.pipeline import run_synthetic_image_detection_analysis
        from core.legacy.synthetic_image_detection.runtime import runtime_status

        ok_runtime, reason = runtime_status()
        if not ok_runtime:
            pytest.skip(reason)

        ok_effort, _ = any_effort_ready()
        if not ok_effort:
            pytest.skip("Pesos Effort ausentes")

        image = Image.open(AUTHENTIC).convert("RGB")
        out = run_synthetic_image_detection_analysis(image, generate_visuals=False)
        names = [r[0] for r in out["individual_results"]]
        assert any("GenImage" in n for n in names)
        assert any("Chameleon" in n for n in names)
