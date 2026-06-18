"""Unit tests for Low-Res Fake Video (TUM / LFV)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

WORKSPACE = Path(__file__).resolve().parents[2]


def test_lfv_vendor_isolation_after_distildire():
    """LFV deve importar networks/xception mesmo apos DistilDIRE carregar networks."""
    import importlib.util

    distildire = WORKSPACE / "vendor" / "distildire"
    if not distildire.is_dir():
        pytest.skip("vendor/distildire ausente")

    from core.legacy.distildire.distildire_vendor import distildire_vendor_context

    with distildire_vendor_context():
        spec = importlib.util.find_spec("networks.distill_model")
        assert spec is not None and "distildire" in (spec.origin or "")

    from core.legacy.lowres_fake_video.lfv_vendor import lfv_vendor_context

    vendor = WORKSPACE / "vendor" / "fake-video-detection"
    if not vendor.is_dir():
        pytest.skip("vendor/fake-video-detection ausente")

    with lfv_vendor_context():
        from networks import xception as xception_mod
        from networks.baseline import BaselineModel

    assert "xception" in xception_mod.__file__
    assert BaselineModel.__module__ == "networks.baseline"


def test_lfv_runtime_status():
    from core.legacy.lowres_fake_video.lfv_runtime import lfv_runtime_status

    ok, reason = lfv_runtime_status()
    assert isinstance(ok, bool)
    assert isinstance(reason, str)
    weight = WORKSPACE / "models" / "lowres_fake_video" / "weights" / "baseline_xception.pt"
    if weight.is_file():
        assert ok, reason


def test_lfv_checkpoint_maps_deepfakebench_weights():
    import torch
    import torch.nn as nn

    from core.legacy.lowres_fake_video.lfv_pipeline import _map_checkpoint_to_baseline, clear_lfv_model_cache
    from core.legacy.lowres_fake_video.lfv_runtime import weight_path

    clear_lfv_model_cache()
    wp = weight_path()
    if not wp.is_file():
        pytest.skip("pesos LFV ausentes")

    raw = torch.load(wp, map_location="cpu", weights_only=False)
    mapped, input_size = _map_checkpoint_to_baseline(raw)
    assert input_size == 256
    assert mapped["model.conv1.weight"] is not None
    assert mapped["model.last_linear.weight"].shape == (2, 2048)

    from core.legacy.lowres_fake_video.lfv_vendor import lfv_vendor_context

    vendor = WORKSPACE / "vendor" / "fake-video-detection"
    if not vendor.is_dir():
        pytest.skip("vendor/fake-video-detection ausente")

    with lfv_vendor_context():
        from networks import xception as xception_mod
        from networks.baseline import BaselineModel

        backbone = xception_mod.xception(pretrained=False)
        backbone.last_linear = nn.Linear(backbone.last_linear.in_features, 2)
        model = BaselineModel.__new__(BaselineModel)
        nn.Module.__init__(model)
        model.model_choice = "xception"
        model.model = backbone
        msg = model.load_state_dict(mapped, strict=False)
        assert not msg.missing_keys


def test_lfv_scores_vary_across_frames():
    """Com pesos carregados corretamente, frames distintos nao devem colapsar em ~0.495."""
    import tempfile

    import cv2
    import numpy as np

    from core.legacy.lowres_fake_video.lfv_pipeline import clear_lfv_model_cache, run_lfv_analysis
    from core.legacy.lowres_fake_video.lfv_runtime import lfv_runtime_status

    ok, reason = lfv_runtime_status()
    if not ok:
        pytest.skip(reason)

    clear_lfv_model_cache()
    tmpdir = Path(tempfile.mkdtemp())
    video = tmpdir / "vary.mp4"
    w, h, n = 320, 240, 40
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    vw = cv2.VideoWriter(str(video), fourcc, 10.0, (w, h))
    for i in range(n):
        frame = np.zeros((h, w, 3), dtype=np.uint8)
        frame[:, :, 0] = int(255 * i / max(1, n - 1))
        frame[:, :, 1] = int(128 + 127 * np.sin(i / 3))
        cv2.rectangle(frame, (60 + i, 30), (220, 200), (200, 180, 160), -1)
        vw.write(frame)
    vw.release()

    analysis = run_lfv_analysis(str(video), sample_every=2, max_frames=12, out_dir=tmpdir / "out")
    scores = [f.score for f in analysis.frame_scores]
    assert len(scores) >= 4
    assert max(scores) - min(scores) > 0.001, f"scores colapsaram: {scores[:6]}"


def test_lfv_plugin_simulated(monkeypatch, tmp_path):
    from core.legacy.lowres_fake_video.lfv_pipeline import FrameScore, LfvAnalysis
    from core.plugins.lowres_fake_video_plugin import LowResFakeVideoPlugin

    monkeypatch.setattr(
        "core.plugins.lowres_fake_video_plugin.lfv_runtime_status",
        lambda: (True, ""),
    )

    fake = LfvAnalysis(
        video_decision="Real",
        mean_score=0.42,
        max_score=0.48,
        max_frame_idx=10,
        frame_scores=[FrameScore(frame_idx=10, score=0.48, decision="Real")],
        scores_chart_path=None,
        inference_device="CPU",
    )

    def _fake_run(*_a, **_k):
        out = Path(_k.get("out_dir") or tmp_path)
        out.mkdir(parents=True, exist_ok=True)
        return fake

    monkeypatch.setattr("core.plugins.lowres_fake_video_plugin.run_lfv_analysis", _fake_run)

    evidence = tmp_path / "sample.mp4"
    evidence.write_bytes(b"\x00" * 128)

    plugin = LowResFakeVideoPlugin()
    result = plugin.analyze(
        str(evidence),
        {"sample_every": 5, "max_frames": 10, "_job_staging_dir": str(tmp_path / "out")},
    )
    assert result["success"] is True
    assert result["video_decision"] == "Real"
    assert Path(result["lfv_report_json_path"]).is_file()
