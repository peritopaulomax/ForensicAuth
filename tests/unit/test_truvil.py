"""Unit tests for TruVIL video inpainting localization."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

WORKSPACE = Path(__file__).resolve().parents[2]


def test_truvil_runtime_status_shape():
    from forensics.truvil.truvil_runtime import truvil_runtime_status

    ok, reason = truvil_runtime_status()
    assert isinstance(ok, bool)
    assert isinstance(reason, str)
    weight = WORKSPACE / "models" / "truvil" / "weights" / "TruVIL_train_VI_OP.pth"
    vendor = WORKSPACE / "vendor" / "truvil"
    if weight.is_file() and vendor.is_dir():
        assert ok, reason


def test_truvil_plugin_registered():
    from core.plugin_registry import PluginRegistry

    reg = PluginRegistry()
    plugins_dir = WORKSPACE / "src" / "backend" / "core" / "plugins"
    reg.discover_and_register(str(plugins_dir))
    assert "truvil" in reg.list_plugins()
    plugin = reg.PLUGINS["truvil"]()
    assert plugin.supported_types == ["video"]


def test_truvil_validate_parameters():
    from core.plugins.truvil_plugin import TruVilPlugin

    plugin = TruVilPlugin()
    with patch(
        "core.plugins.truvil_plugin.truvil_runtime_status",
        return_value=(True, ""),
    ):
        ok, msg = plugin.validate_parameters({"sample_every": 5, "max_clips": 8})
        assert ok, msg
        bad, _ = plugin.validate_parameters({"sample_every": 0, "max_clips": 8})
        assert not bad
        bad2, _ = plugin.validate_parameters({"sample_every": 5, "max_clips": 8, "clip_len": 4})
        assert not bad2


def test_truvil_analyze_mocked(tmp_path):
    from core.plugins.truvil_plugin import TruVilPlugin
    from forensics.truvil.truvil_pipeline import ClipResult, TruVilAnalysis

    fake = TruVilAnalysis(
        mean_mask_ratio=0.02,
        max_mask_ratio=0.05,
        max_start_frame=0,
        threshold=0.5,
        clip_results=[ClipResult(start_frame=0, mean_mask_ratio=0.02, max_mask_ratio=0.05)],
        scores_chart_path=str(tmp_path / "chart.png"),
        overlay_preview_path=str(tmp_path / "ov.png"),
        mask_preview_path=str(tmp_path / "mk.png"),
        heatmap_preview_path=str(tmp_path / "hm.png"),
        inference_device="CPU",
    )
    for name in ("chart.png", "ov.png", "mk.png", "hm.png"):
        (tmp_path / name).write_bytes(b"x")

    plugin = TruVilPlugin()
    with (
        patch("core.plugins.truvil_plugin.truvil_runtime_status", return_value=(True, "")),
        patch("core.plugins.truvil_plugin.run_truvil_analysis", return_value=fake),
        patch(
            "core.plugins.truvil_plugin.write_truvil_report",
            return_value=(str(tmp_path / "truvil_report.json"), str(tmp_path / "truvil_summary.txt")),
        ),
        patch("core.plugins.truvil_plugin.job_artifact_dir", return_value=tmp_path),
    ):
        result = plugin.analyze("/tmp/fake.mp4", {"sample_every": 5, "max_clips": 4})

    assert result["success"] is True
    assert "decision" not in result
    assert "video_decision" not in result
    assert result["mean_mask_ratio"] == 0.02
    assert "truvil_report_json_path" in result
    assert result.get("truvil_heatmap_preview_path")


def test_truvil_remap_checkpoint_keys():
    from forensics.truvil.truvil_pipeline import _remap_checkpoint_keys

    remapped = _remap_checkpoint_keys(
        {
            "encoder.tacf.conv1.0.weight": 1,
            "rgd.gamma": 2,
            "encoder.blocks.0.weight": 3,
        }
    )
    assert remapped["encoder.CAF.conv1.0.weight"] == 1
    assert remapped["AND.gamma"] == 2
    assert remapped["encoder.blocks.0.weight"] == 3


@pytest.mark.weights
@pytest.mark.gpu
def test_truvil_forward_smoke(tmp_path):
    import numpy as np
    import cv2

    from forensics.truvil.truvil_pipeline import clear_truvil_model_cache, run_truvil_analysis
    from forensics.truvil.truvil_runtime import truvil_runtime_status

    ok, reason = truvil_runtime_status()
    if not ok:
        pytest.skip(reason)

    video = tmp_path / "tiny.mp4"
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"mp4v"), 5, (64, 64))
    assert writer.isOpened()
    for i in range(12):
        frame = np.full((64, 64, 3), (i * 20) % 255, dtype=np.uint8)
        writer.write(frame)
    writer.release()

    clear_truvil_model_cache()
    out = tmp_path / "out"
    analysis = run_truvil_analysis(
        str(video),
        sample_every=1,
        max_clips=2,
        clip_len=5,
        out_dir=out,
    )
    assert analysis.clip_results
    assert 0.0 <= analysis.mean_mask_ratio <= 1.0
    assert (out / "truvil_mask_preview.png").is_file() or analysis.mask_preview_path
    assert (out / "truvil_heatmap_preview.png").is_file() or analysis.heatmap_preview_path
