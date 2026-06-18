"""Tests for preview-tier job receipts and promoted reproducibility."""

import hashlib
import json
from pathlib import Path

import cv2
import numpy as np

from core.reproducibility import (
    build_job_execution_receipt,
    build_promoted_reproducibility_record,
    build_runtime_manifest,
    compare_execution_receipt,
    load_job_execution_receipt,
)
from services.custody_utils import hash_canonical_json


class TestJobPreviewReproducibility:
    def test_lightweight_manifest_skips_model_hashes_for_ela(self, tmp_path):
        runtime = build_runtime_manifest(
            app_version="0.2.0",
            gpu_available=False,
            models_dir=str(tmp_path / "models"),
            technique="ela",
        )
        assert "model_file_hashes" not in runtime

    def test_job_execution_receipt_stable_digest(self):
        runtime = build_runtime_manifest(
            app_version="0.2.0",
            gpu_available=False,
            models_dir="/tmp/models",
        )
        result = {"success": True, "mean_score": 0.42, "timestamp": "ignore-me"}
        r1 = build_job_execution_receipt(
            technique="safire",
            result=result,
            runtime_manifest=runtime,
            job_id="abc",
            parameters={"mode": "binary"},
            input_evidence_sha256="deadbeef",
        )
        r2 = build_job_execution_receipt(
            technique="safire",
            result=result,
            runtime_manifest=runtime,
            job_id="abc",
            parameters={"mode": "binary"},
            input_evidence_sha256="deadbeef",
        )
        assert r1["kind"] == "job_execution_receipt"
        assert r1["execution_digest"] == r2["execution_digest"]
        assert r1["determinism_profile"] == "gpu_ml"

    def test_promoted_reproducibility_hashes_file(self, tmp_path):
        artifact = tmp_path / "heatmap.png"
        cv2.imwrite(str(artifact), np.ones((8, 8, 3), dtype=np.uint8) * 200)
        runtime = build_runtime_manifest(
            app_version="0.2.0",
            gpu_available=True,
            models_dir=str(tmp_path),
        )
        receipt = build_job_execution_receipt(
            technique="ela",
            result={"success": True, "ela_score": 1.0},
            runtime_manifest=runtime,
        )
        promoted = build_promoted_reproducibility_record(
            technique="ela",
            job_receipt=receipt,
            artifact_path=artifact,
            artifact_filename="heatmap.png",
        )
        assert promoted["kind"] == "promoted_derivative"
        assert promoted["artifact_sha256"] == hashlib.sha256(artifact.read_bytes()).hexdigest()
        assert promoted["job_execution_receipt"]["execution_digest"] == receipt["execution_digest"]

    def test_load_job_execution_receipt_from_result_json(self):
        runtime = {"runtime_schema_version": "1", "forensicauth_version": "1.0"}
        payload = {
            "job_receipt": {
                "kind": "job_execution_receipt",
                "execution_digest": "abc123",
                "runtime": runtime,
            }
        }
        loaded = load_job_execution_receipt(payload, None)
        assert loaded is not None
        assert loaded["execution_digest"] == "abc123"

    def test_compare_execution_receipt_match(self):
        runtime = build_runtime_manifest(
            app_version="1.0.0",
            gpu_available=False,
            models_dir="/tmp/m",
            image_digest="sha256:1",
        )
        receipt = build_job_execution_receipt(
            technique="mock_technique",
            result={"success": True, "value": 1},
            runtime_manifest=runtime,
        )
        report = compare_execution_receipt(
            technique="mock_technique",
            original_receipt=receipt,
            reproduced_receipt=receipt,
            current_runtime=runtime,
        )
        assert report["status"] == "MATCH"
        assert report["comparison_mode"] == "execution_receipt"
