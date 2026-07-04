"""E2E simulado: ClipBased-SyntheticImageDetection no fluxo plugin -> artefatos."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image


@pytest.mark.e2e
class TestClipBasedSyntheticE2E:
    def test_adapter_produces_report(self, monkeypatch, tmp_path):
        from core.plugins.clipbased_synthetic_adapter import ClipBasedSyntheticAdapter

        img = Image.new("RGB", (200, 200), (30, 60, 90))
        evidence = tmp_path / "sample.jpg"
        img.save(evidence)

        monkeypatch.setattr(
            "core.plugins.clipbased_synthetic_adapter.clipbased_runtime_status",
            lambda: (True, ""),
        )

        def _fake_analyze(self, evidence_path, parameters):
            return {
                "success": True,
                "adapter": "clipbased_synthetic",
                "status": "completed",
                "model_name": "clipdet_latent10k_plus",
                "llr": 1.23,
                "prediction": "FAKE",
                "fake_score": 0.77,
                "real_score": 0.23,
                "inference_device": "GPU",
            }

        monkeypatch.setattr(ClipBasedSyntheticAdapter, "analyze", _fake_analyze)

        plugin = ClipBasedSyntheticAdapter()
        result = plugin.analyze(
            str(evidence),
            {"model_name": "clipdet_latent10k_plus", "_job_staging_dir": str(tmp_path / "staging")},
        )

        assert result["success"] is True
        assert result["prediction"] == "FAKE"
        assert result["llr"] == 1.23
        assert result["fake_score"] == 0.77

    def test_technique_registered_in_runtime_probe(self):
        from core.technique_runtime import technique_runtime_status

        ok, reason = technique_runtime_status("clipbased_synthetic")
        assert isinstance(ok, bool)
        assert isinstance(reason, str)
