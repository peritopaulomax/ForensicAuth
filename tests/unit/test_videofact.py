"""Unit tests for VideoFACT integration."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

WORKSPACE = Path(__file__).resolve().parents[2]


def test_videofact_runtime_missing_weights():
    from core.legacy.videofact import videofact_runtime as vr

    ok, reason = vr.videofact_runtime_status()
    if (WORKSPACE / "models" / "videofact" / "weights" / "videofact_xfer.ckpt").is_file():
        assert ok or "df" in reason.lower() or reason == ""
    else:
        assert not ok
        assert "videofact" in reason.lower() or "peso" in reason.lower()


def test_videofact_plugin_validate_mode(monkeypatch):
    from core.plugins.videofact_plugin import VideoFactPlugin

    monkeypatch.setattr(
        "core.plugins.videofact_plugin.videofact_runtime_status",
        lambda **_: (True, ""),
    )
    plugin = VideoFactPlugin()
    ok, msg = plugin.validate_parameters({"mode": "invalid"})
    assert not ok
    assert "mode" in msg


@pytest.mark.e2e
def test_videofact_adapter_simulated(monkeypatch, tmp_path):
    from core.plugins.videofact_plugin import VideoFactPlugin
    from core.legacy.videofact.videofact_pipeline import ModeResult, VideoFactAnalysis

    monkeypatch.setattr(
        "core.plugins.videofact_plugin.videofact_runtime_status",
        lambda **_: (True, ""),
    )

    fake_analysis = VideoFactAnalysis(
        modes=[
            ModeResult(
                mode="xfer",
                model_label="VideoFACT (Edicoes/Xfer)",
                threshold=0.4,
                video_decision="Authentic",
                mean_score=0.2,
                max_score=0.35,
                max_frame_idx=10,
                frame_results=[],
                inference_device="CPU",
            )
        ],
        total_frames_sampled=5,
        sample_every=5,
        inference_device="CPU",
    )

    monkeypatch.setattr(
        "core.plugins.videofact_plugin.run_videofact_analysis",
        lambda *a, **k: fake_analysis,
    )

    evidence = tmp_path / "sample.mp4"
    evidence.write_bytes(b"\x00" * 128)

    plugin = VideoFactPlugin()
    result = plugin.analyze(
        str(evidence),
        {"mode": "xfer", "_job_staging_dir": str(tmp_path / "out")},
    )
    assert result["success"] is True
    assert result["videofact_xfer_decision"] == "Authentic"
    assert Path(result["videofact_report_json_path"]).is_file()
