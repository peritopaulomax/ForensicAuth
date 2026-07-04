"""Tests for runtime manifest and artifact hashing."""

import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from core.reproducibility import (
    MODEL_HASH_CACHE_FILENAME,
    REPRODUCIBILITY_REGISTRY,
    _model_file_hashes,
    _model_hash_cache_path,
    build_job_execution_receipt,
    build_reproducibility_record,
    build_runtime_manifest,
    clear_model_file_hash_cache,
    compare_reproduction,
    compute_artifact_sha256,
)
from services.custody_utils import hash_canonical_json


class TestRuntimeManifest:
    def test_model_file_hashes_cached_until_mtime_changes(self, tmp_path):
        models = tmp_path / "models"
        models.mkdir()
        weight = models / "demo.pth"
        weight.write_bytes(b"weight-v1")

        clear_model_file_hash_cache()
        first = _model_file_hashes(str(models))
        second = _model_file_hashes(str(models))
        assert first == second

        weight.write_bytes(b"weight-v2-longer-content")
        third = _model_file_hashes(str(models))
        assert third != first

    def test_persistent_cache_created_and_reused_across_restarts(self, tmp_path, monkeypatch):
        models = tmp_path / "models"
        models.mkdir()
        weight = models / "demo.pth"
        weight.write_bytes(b"weight-v1")

        clear_model_file_hash_cache()
        first = _model_file_hashes(str(models))
        cache_path = _model_hash_cache_path(str(models))
        assert cache_path.is_file()

        clear_model_file_hash_cache()
        sha_calls = []
        original_sha = __import__("core.reproducibility", fromlist=["_sha256_file"])._sha256_file

        def counting_sha(path):
            sha_calls.append(path)
            return original_sha(path)

        monkeypatch.setattr("core.reproducibility._sha256_file", counting_sha)
        second = _model_file_hashes(str(models))
        assert second == first
        assert len(sha_calls) == 0, "persistent cache should be reused without re-hashing files"

    def test_persistent_cache_invalidated_when_model_changes(self, tmp_path):
        models = tmp_path / "models"
        models.mkdir()
        weight = models / "demo.pth"
        weight.write_bytes(b"weight-v1")

        clear_model_file_hash_cache()
        first = _model_file_hashes(str(models))
        assert _model_hash_cache_path(str(models)).is_file()

        clear_model_file_hash_cache()
        weight.write_bytes(b"weight-v2-longer-content")
        second = _model_file_hashes(str(models))
        assert second != first

    def test_persistent_cache_invalidated_when_hmac_tampered(self, tmp_path):
        models = tmp_path / "models"
        models.mkdir()
        weight = models / "demo.pth"
        weight.write_bytes(b"weight-v1")

        clear_model_file_hash_cache()
        first = _model_file_hashes(str(models))
        cache_path = _model_hash_cache_path(str(models))

        data = json.loads(cache_path.read_text(encoding="utf-8"))
        data["hmac"] = "0" * 64
        cache_path.write_text(json.dumps(data), encoding="utf-8")

        clear_model_file_hash_cache()
        second = _model_file_hashes(str(models))
        assert second == first
        # Cache should have been regenerated (HMAC mismatch) and rewritten.
        fresh = json.loads(cache_path.read_text(encoding="utf-8"))
        assert fresh["hmac"] != "0" * 64

    def test_persistent_cache_invalidated_when_schema_version_changes(self, tmp_path):
        models = tmp_path / "models"
        models.mkdir()
        weight = models / "demo.pth"
        weight.write_bytes(b"weight-v1")

        clear_model_file_hash_cache()
        _model_file_hashes(str(models))
        cache_path = _model_hash_cache_path(str(models))

        data = json.loads(cache_path.read_text(encoding="utf-8"))
        data["cache_schema_version"] = "legacy"
        cache_path.write_text(json.dumps(data), encoding="utf-8")

        clear_model_file_hash_cache()
        second = _model_file_hashes(str(models))
        assert second == {"demo.pth": hashlib.sha256(b"weight-v1").hexdigest()}

    def test_persistent_cache_uses_fallback_key_when_secret_key_missing(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SECRET_KEY", "")
        models = tmp_path / "models"
        models.mkdir()
        weight = models / "demo.pth"
        weight.write_bytes(b"weight-v1")

        clear_model_file_hash_cache()
        first = _model_file_hashes(str(models))
        cache_path = _model_hash_cache_path(str(models))
        assert cache_path.is_file()

        clear_model_file_hash_cache()
        second = _model_file_hashes(str(models))
        assert second == first

    def test_persistent_cache_invalidated_after_system_reboot(self, tmp_path, monkeypatch):
        models = tmp_path / "models"
        models.mkdir()
        weight = models / "demo.pth"
        weight.write_bytes(b"weight-v1")

        clear_model_file_hash_cache()
        monkeypatch.setattr("core.reproducibility._system_boot_time", lambda: 1_000_000)
        first = _model_file_hashes(str(models))
        cache_path = _model_hash_cache_path(str(models))
        assert cache_path.is_file()

        clear_model_file_hash_cache()
        sha_calls = []
        original_sha = __import__("core.reproducibility", fromlist=["_sha256_file"])._sha256_file

        def counting_sha(path):
            sha_calls.append(path)
            return original_sha(path)

        monkeypatch.setattr("core.reproducibility._sha256_file", counting_sha)
        # Simulate a system reboot by changing the reported boot time.
        monkeypatch.setattr("core.reproducibility._system_boot_time", lambda: 2_000_000)
        second = _model_file_hashes(str(models))
        assert second == first
        assert len(sha_calls) == 1, "cache must be invalidated after system reboot and files re-hashed"

    def test_build_runtime_manifest_has_schema_version(self):
        manifest = build_runtime_manifest(
            app_version="1.0.0",
            gpu_available=False,
            models_dir="/tmp/empty-models",
            image_tag="forensicauth:1.0.0-cpu",
            image_digest="sha256:abc",
            worker_queue="celery",
        )
        assert manifest["runtime_schema_version"] == "1"
        assert manifest["forensicauth_version"] == "1.0.0"
        assert manifest["docker_image"] == "forensicauth:1.0.0-cpu"
        assert manifest["docker_image_digest"] == "sha256:abc"
        assert manifest["worker_queue"] == "celery"
        assert "libraries" in manifest
        assert "python" in manifest["libraries"]


class TestArtifactHashing:
    def test_ela_primary_artifact_stable(self, tmp_path):
        heatmap = tmp_path / "heatmap.png"
        img = np.zeros((10, 10, 3), dtype=np.uint8)
        cv2.imwrite(str(heatmap), img)
        result = {"success": True, "ela_score": 1.0}
        h1, profile, name = compute_artifact_sha256("ela", tmp_path, result)
        h2, _, _ = compute_artifact_sha256("ela", tmp_path, result)
        assert profile == "strict"
        assert name == "heatmap.png"
        assert h1 == h2
        assert len(h1) == 64

    def test_synthetic_image_detection_primary_artifact_is_model_scores(self):
        spec = REPRODUCIBILITY_REGISTRY.get("synthetic_image_detection", {})
        assert spec.get("primary") == "model_scores.txt"
        assert spec.get("profile") == "gpu_ml"

    def test_jpeg_structure_compare_in_registry(self):
        spec = REPRODUCIBILITY_REGISTRY.get("jpeg_structure_compare", {})
        assert spec.get("primary") == "jpeg_structure_matrix.json"
        assert spec.get("profile") == "strict"

    def test_job_receipt_survives_int_keys_in_metric_peaks(self):
        """JPEG Ghosts uses int quality keys in metric_peaks_by_quality."""
        result = {
            "success": True,
            "metric_peaks_by_quality": {50: 0.1, 100: 0.9},
            "ghost_map_image_path": "/tmp/ghost.png",
        }
        receipt = build_job_execution_receipt(
            technique="jpeg_ghosts",
            result=result,
            runtime_manifest=build_runtime_manifest(
                app_version="0.2.0",
                gpu_available=False,
                models_dir="/tmp/models",
            ),
        )
        assert receipt["technique"] == "jpeg_ghosts"
        assert receipt["execution_digest"]

    def test_build_reproducibility_record(self, tmp_path):
        heatmap = tmp_path / "heatmap.png"
        cv2.imwrite(str(heatmap), np.ones((5, 5, 3), dtype=np.uint8) * 128)
        runtime = build_runtime_manifest(
            app_version="0.2.0",
            gpu_available=False,
            models_dir=str(tmp_path / "models"),
            image_digest="sha256:deadbeef",
        )
        record = build_reproducibility_record(
            "ela",
            tmp_path,
            {"success": True},
            runtime,
        )
        assert record["technique"] == "ela"
        assert record["determinism_profile"] == "strict"
        assert record["artifact_sha256"]
        assert record["runtime"]["docker_image_digest"] == "sha256:deadbeef"

    def test_compare_reproduction_match(self):
        report = compare_reproduction(
            technique="ela",
            determinism_profile="strict",
            original_artifact_sha256="abc",
            reproduced_artifact_sha256="abc",
            original_runtime={"docker_image_digest": "sha256:1"},
            current_runtime={"docker_image_digest": "sha256:1"},
        )
        assert report["status"] == "MATCH"
        assert report["artifact_match"] is True

    def test_compare_reproduction_parallel_mismatch(self):
        report = compare_reproduction(
            technique="prnu",
            determinism_profile="parallel",
            original_artifact_sha256="aaa",
            reproduced_artifact_sha256="bbb",
            original_runtime={},
            current_runtime={},
        )
        assert report["status"] == "BEST_EFFORT_MISMATCH"

    def test_registry_covers_production_techniques(self):
        expected = {
            "ela",
            "prnu",
            "synthetic_image_detection",
            "mp3_parser",
            "isomedia_parser",
            "pdf_forensic_extract",
        }
        assert expected.issubset(REPRODUCIBILITY_REGISTRY.keys())
