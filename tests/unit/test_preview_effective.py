"""Tests for preview effective parameters and materialization."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import cv2
import numpy as np
import pytest

from core.plugins.ela_plugin import BASE_ELA_SCALE
from core.preview_cleanup_policy import (
    maybe_cleanup_expired_job_previews,
    reset_cleanup_throttle_for_tests,
)
from core.preview_effective import (
    merge_effective_parameters,
    persist_effective_parameters,
    record_promoted_derivative,
    sync_job_runtime_receipt,
)
from core.preview_materialize import (
    materialize_ela_heatmap,
    materialize_imdl_mask,
    materialize_wavelet_noise_residue,
)
from models.analysis_job import AnalysisJob


class TestPreviewEffective:
    def test_merge_effective_parameters_layers_override(self):
        job = AnalysisJob(
            id=uuid.uuid4(),
            evidence_id=uuid.uuid4(),
            technique="ela",
            status="completed",
            parameters={"quality": 95, "gain": 1.0},
            created_by=uuid.uuid4(),
        )
        merged = merge_effective_parameters(
            job,
            {"effective_parameters": {"gain": 2.5, "channel_mode": "y"}},
            override={"gain": 3.0},
        )
        assert merged["quality"] == 95
        assert merged["gain"] == 3.0
        assert merged["channel_mode"] == "y"

    def test_persist_effective_parameters_writes_result_json(self, tmp_path: Path):
        result_path = tmp_path / "result.json"
        result_path.write_text(json.dumps({"success": True}), encoding="utf-8")
        payload = persist_effective_parameters(tmp_path, {"gain": 2.0, "quality": 90})
        assert payload["effective_parameters"]["gain"] == 2.0
        loaded = json.loads(result_path.read_text(encoding="utf-8"))
        assert loaded["effective_parameters"]["quality"] == 90


class TestPreviewMaterialize:
    def test_materialize_ela_heatmap_applies_gain(self, tmp_path: Path):
        base = np.full((4, 4, 3), 30, dtype=np.uint8)
        cv2.imwrite(str(tmp_path / "heatmap_base.png"), base)
        materialize_ela_heatmap(tmp_path, gain=2.0)
        out = cv2.imread(str(tmp_path / "heatmap.png"))
        assert out is not None
        expected = int(min(255, round((30 / BASE_ELA_SCALE) * 2.0 * BASE_ELA_SCALE)))
        assert int(out[0, 0, 0]) == expected

    def test_materialize_imdl_mask_threshold(self, tmp_path: Path):
        scores = np.array([[50, 200], [100, 255]], dtype=np.uint8)
        cv2.imwrite(str(tmp_path / "score_map.png"), scores)
        materialize_imdl_mask(tmp_path, threshold=0.5)
        mask = cv2.imread(str(tmp_path / "mask.png"), cv2.IMREAD_GRAYSCALE)
        assert mask is not None
        assert int(mask[0, 0]) == 0
        assert int(mask[0, 1]) == 255
        assert int(mask[1, 0]) == 0
        assert int(mask[1, 1]) == 255

    def test_materialize_wavelet_reprocesses_from_npz(self, tmp_path: Path):
        from core.legacy.wavelet_noise_residue import run_wavelet_noise_residue

        gray = np.random.default_rng(3).integers(30, 200, (64, 64), dtype=np.uint8)
        npz_path = tmp_path / "wnr_dwt_coefficients.npz"
        run_wavelet_noise_residue(gray, {"order": 8, "blocksize": 3, "thr": 255}, dwt_coefficients_path=npz_path)
        stale = np.zeros((64, 64, 3), dtype=np.uint8)
        cv2.imwrite(str(tmp_path / "overlay.png"), stale)

        materialize_wavelet_noise_residue(tmp_path, {"blocksize": 3, "thr": 64, "post": True})
        overlay = cv2.imread(str(tmp_path / "overlay.png"))
        assert overlay is not None
        assert int(np.max(overlay)) > 0

    def test_sync_job_runtime_receipt_updates_parameters(self, tmp_path: Path):
        job = AnalysisJob(
            id=uuid.uuid4(),
            evidence_id=uuid.uuid4(),
            technique="ela",
            status="completed",
            parameters={"gain": 1.0},
            runtime_manifest={
                "kind": "job_execution_receipt",
                "parameters": {"gain": 1.0},
            },
            created_by=uuid.uuid4(),
        )
        payload = {
            "job_receipt": {
                "kind": "job_execution_receipt",
                "parameters": {"gain": 1.0},
            }
        }
        (tmp_path / "result.json").write_text(json.dumps(payload), encoding="utf-8")
        sync_job_runtime_receipt(job, tmp_path, {"gain": 2.5, "quality": 90})
        assert job.runtime_manifest["parameters"]["gain"] == 2.5
        loaded = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
        assert loaded["job_receipt"]["parameters"]["gain"] == 2.5

    def test_record_promoted_derivative_appends_entry(self, tmp_path: Path):
        (tmp_path / "result.json").write_text(json.dumps({"success": True}), encoding="utf-8")
        record_promoted_derivative(
            tmp_path,
            evidence_id="ev-1",
            artifact_filename="heatmap.png",
            sha256="abc",
            label="test",
        )
        loaded = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
        assert loaded["promoted"] is True
        assert len(loaded["promoted_derivatives"]) == 1
        assert loaded["promoted_derivatives"][0]["artifact_filename"] == "heatmap.png"


class TestPreviewCleanupPolicy:
    def test_cleanup_throttled_within_interval(self, monkeypatch):
        import core.preview_cleanup_policy as policy

        policy.reset_cleanup_throttle_for_tests()
        calls: list[int] = []

        def _fake_cleanup(db=None):
            calls.append(1)
            return 0

        monkeypatch.setattr(policy, "cleanup_expired_job_previews", _fake_cleanup)
        assert policy.maybe_cleanup_expired_job_previews() == 0
        assert len(calls) == 1
        assert policy.maybe_cleanup_expired_job_previews() == 0
        assert len(calls) == 1

    def test_cleanup_removes_promoted_preview_folder(self, tmp_path: Path, monkeypatch):
        from core.preview_cleanup import cleanup_expired_job_previews

        job_dir = tmp_path / str(uuid.uuid4())
        job_dir.mkdir()
        result_path = job_dir / "result.json"
        result_path.write_text(
            json.dumps({"preview": True, "promoted": True}),
            encoding="utf-8",
        )
        old = (datetime.now(timezone.utc) - timedelta(days=10)).timestamp()
        import os

        settings = type(
            "S",
            (),
            {"RESULTS_DIR": str(tmp_path), "JOB_PREVIEW_RETENTION_DAYS": 7},
        )()
        monkeypatch.setattr("core.preview_cleanup.get_settings", lambda: settings)
        os.utime(result_path, (old, old))

        assert cleanup_expired_job_previews() == 1
        assert not job_dir.exists()
