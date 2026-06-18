"""E2E simulado: DistilDIRE no fluxo plugin → artefatos."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image


@pytest.mark.e2e
class TestDistilDireE2E:
    def test_adapter_produces_report_and_images(self, monkeypatch, tmp_path):
        from core.legacy.distildire.distildire_pipeline import DistilDireAnalysis
        from core.plugins.distildire_plugin import DistilDirePlugin

        img = Image.new("RGB", (200, 200), (30, 60, 90))
        evidence = tmp_path / "sample.jpg"
        img.save(evidence)

        monkeypatch.setattr(
            "core.plugins.distildire_plugin.distildire_runtime_status",
            lambda **_: (True, ""),
        )
        monkeypatch.setattr(
            "core.plugins.distildire_plugin.run_distildire_analysis",
            lambda *a, **k: DistilDireAnalysis(
                df_probability=0.31,
                prediction="REAL",
                threshold=0.5,
                checkpoint="imagenet",
                input_image=img,
                eps_heatmap=img.convert("L"),
                inference_device="CPU",
            ),
        )

        plugin = DistilDirePlugin()
        out = tmp_path / "staging"
        out.mkdir()
        result = plugin.analyze(
            str(evidence),
            {
                "_job_staging_dir": str(out),
                "checkpoint": "imagenet",
                "threshold": 0.5,
                "generate_visuals": True,
            },
        )

        assert result["success"] is True
        assert result["prediction"] == "REAL"
        report = Path(result["distildire_report_json_path"])
        assert report.is_file()
        assert "distildire_report.json" in report.name
        assert result.get("input_image_path")
        assert result.get("distildire_eps_heatmap_path")

    def test_technique_registered_in_runtime_probe(self):
        from core.technique_runtime import technique_runtime_status

        ok, reason = technique_runtime_status("distildire")
        assert isinstance(ok, bool)
        assert isinstance(reason, str)
