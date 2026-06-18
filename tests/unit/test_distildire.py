"""Unit and integration tests for DistilDIRE."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PIL import Image


WORKSPACE = Path(__file__).resolve().parents[2]
FIXTURE = WORKSPACE / "uploads-dev" / "7bab0877-d873-4b68-aad9-de2e79ca14e7.jpg"


def test_distildire_vendor_isolation_after_lfv():
    """DistilDIRE deve resolver networks/distill_model apos LFV carregar networks."""
    import importlib.util

    lfv_vendor = WORKSPACE / "vendor" / "fake-video-detection"
    if not lfv_vendor.is_dir():
        pytest.skip("vendor/fake-video-detection ausente")

    from core.legacy.lowres_fake_video.lfv_vendor import lfv_vendor_context

    with lfv_vendor_context():
        from networks import xception as xception_mod  # noqa: F401

    distildire = WORKSPACE / "vendor" / "distildire"
    if not distildire.is_dir():
        pytest.skip("vendor/distildire ausente")

    from core.legacy.distildire.distildire_vendor import distildire_vendor_context

    with distildire_vendor_context():
        spec = importlib.util.find_spec("networks.distill_model")

    assert spec is not None
    assert spec.origin is not None
    assert "distildire" in spec.origin


class TestDistilDireRuntime:
    def test_vendor_dir_exists(self):
        from core.legacy.distildire.distildire_runtime import distildire_vendor_dir

        vendor = distildire_vendor_dir()
        assert vendor.is_dir()
        assert (vendor / "networks" / "distill_model.py").is_file()

    def test_runtime_status_without_weights(self, monkeypatch, tmp_path):
        from core.legacy.distildire import distildire_runtime as rt

        monkeypatch.setattr(rt, "distildire_weights_dir", lambda: tmp_path / "weights")
        monkeypatch.setattr(rt, "adm_model_path", lambda: tmp_path / "weights" / rt.ADM_FILE)
        monkeypatch.setattr(
            rt, "checkpoint_path", lambda kind="imagenet": tmp_path / "weights" / rt.CHECKPOINT_FILES[kind]
        )
        rt.distildire_runtime_status.cache_clear()
        ok, reason = rt.distildire_runtime_status()
        assert not ok
        assert "ADM" in reason or "ausente" in reason.lower()
        rt.distildire_runtime_status.cache_clear()


class TestDistilDirePlugin:
    def test_validate_parameters(self, monkeypatch):
        from core.plugins.distildire_plugin import DistilDirePlugin

        monkeypatch.setattr(
            "core.plugins.distildire_plugin.distildire_runtime_status",
            lambda **_: (True, ""),
        )
        plugin = DistilDirePlugin()
        ok, _ = plugin.validate_parameters({"checkpoint": "imagenet", "threshold": 0.5})
        assert ok
        ok, msg = plugin.validate_parameters({"checkpoint": "invalid"})
        assert not ok
        assert "checkpoint" in msg

    def test_analyze_mocked(self, monkeypatch, tmp_path):
        from core.legacy.distildire.distildire_pipeline import DistilDireAnalysis
        from core.plugins.distildire_plugin import DistilDirePlugin

        img = Image.new("RGB", (128, 128), (40, 80, 120))
        evidence = tmp_path / "ev.jpg"
        img.save(evidence)

        analysis = DistilDireAnalysis(
            df_probability=0.82,
            prediction="FAKE",
            threshold=0.5,
            checkpoint="imagenet",
            input_image=img,
            eps_heatmap=img,
            inference_device="GPU",
        )

        monkeypatch.setattr(
            "core.plugins.distildire_plugin.distildire_runtime_status",
            lambda **_: (True, ""),
        )
        monkeypatch.setattr(
            "core.plugins.distildire_plugin.run_distildire_analysis",
            lambda *a, **k: analysis,
        )

        plugin = DistilDirePlugin()
        result = plugin.analyze(
            str(evidence),
            {"_job_staging_dir": str(tmp_path / "out"), "checkpoint": "imagenet", "threshold": 0.5},
        )
        assert result["success"] is True
        assert result["df_probability"] == 0.82
        assert result["prediction"] == "FAKE"
        assert Path(result["distildire_report_json_path"]).is_file()


@pytest.mark.integration
class TestDistilDireIntegration:
    def test_smoke_inference_when_weights_available(self):
        from core.legacy.distildire.distildire_pipeline import run_distildire_analysis
        from core.legacy.distildire.distildire_runtime import distildire_runtime_status

        distildire_runtime_status.cache_clear()
        ok, reason = distildire_runtime_status()
        if not ok:
            pytest.skip(reason or "pesos DistilDIRE ausentes")

        img_path = FIXTURE if FIXTURE.is_file() else None
        if img_path is None:
            tmp = Path("/tmp/distildire_smoke.jpg")
            Image.new("RGB", (256, 256), (100, 150, 200)).save(tmp)
            img_path = tmp

        result = run_distildire_analysis(str(img_path), generate_visuals=False)
        assert 0.0 <= result.df_probability <= 1.0
        assert result.prediction in ("REAL", "FAKE")
