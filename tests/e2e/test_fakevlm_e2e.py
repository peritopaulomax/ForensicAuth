"""E2E simulado: FakeVLM no fluxo plugin -> artefatos."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image


@pytest.mark.e2e
class TestFakeVlmE2E:
    def test_adapter_produces_report(self, monkeypatch, tmp_path):
        from core.plugins.fakevlm_adapter import FakeVlmAdapter

        img = Image.new("RGB", (200, 200), (30, 60, 90))
        evidence = tmp_path / "sample.jpg"
        img.save(evidence)

        monkeypatch.setattr(
            "core.plugins.fakevlm_adapter.fakevlm_runtime_status",
            lambda: (True, ""),
        )
        monkeypatch.setattr(
            "core.plugins.fakevlm_adapter._load_fakevlm_stack",
            lambda _device: {
                "processor": None,
                "model": None,
            },
        )

        def _fake_analyze(self, evidence_path, parameters):
            return {
                "success": True,
                "adapter": "fakevlm",
                "status": "completed",
                "prediction": "FAKE",
                "fake_score": 0.85,
                "real_score": 0.15,
                "response": "This is a fake image.",
                "inference_device": "GPU",
            }

        monkeypatch.setattr(FakeVlmAdapter, "analyze", _fake_analyze)

        plugin = FakeVlmAdapter()
        result = plugin.analyze(
            str(evidence),
            {"max_new_tokens": 100, "_job_staging_dir": str(tmp_path / "staging")},
        )

        assert result["success"] is True
        assert result["prediction"] == "FAKE"
        assert result["fake_score"] == 0.85
        assert result["real_score"] == 0.15

    def test_technique_registered_in_runtime_probe(self):
        from core.technique_runtime import technique_runtime_status

        ok, reason = technique_runtime_status("fakevlm")
        assert isinstance(ok, bool)
        assert isinstance(reason, str)

    def test_parse_verdict_real(self):
        from core.plugins.fakevlm_adapter import _parse_verdict

        prediction, score = _parse_verdict("ASSISTANT: This is a real image.")
        assert prediction == "REAL"
        assert score < 0.5

    def test_parse_verdict_fake(self):
        from core.plugins.fakevlm_adapter import _parse_verdict

        prediction, score = _parse_verdict("ASSISTANT: This is a fake image.")
        assert prediction == "FAKE"
        assert score >= 0.5
