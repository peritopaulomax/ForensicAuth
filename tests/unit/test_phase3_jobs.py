"""Phase 3 job reproducibility and directory layout tests.

Tests for divergences FJ-02, FJ-03, FJ-05, FJ-07, FJ-09, FJ-10.
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from models.analysis_job import AnalysisJob
from services.job_service import JobService, build_job_result_dir


class TestJobResultDirectory:
    def test_run_job_uses_canonical_directory_layout(
        self, db_session, sample_case, sample_evidence, test_user
    ):
        service = JobService(db_session)
        job = service.submit_job(
            evidence_id=sample_evidence.id,
            technique="mock_technique",
            parameters={},
            user_id=test_user.id,
        )
        service.run_job(job.id)

        expected_dir = build_job_result_dir(
            service.settings.RESULTS_DIR,
            sample_case.id,
            sample_evidence.id,
            job.id,
        )
        assert expected_dir.is_dir()
        assert (expected_dir / "result.json").is_file()

    def test_artifact_sha256_is_populated(
        self, db_session, sample_case, sample_evidence, test_user
    ):
        service = JobService(db_session)
        job = service.submit_job(
            evidence_id=sample_evidence.id,
            technique="mock_technique",
            parameters={},
            user_id=test_user.id,
        )
        service.run_job(job.id)

        updated = service.get_job(job.id)
        assert updated.artifact_sha256 is not None
        assert len(updated.artifact_sha256) == 64


class TestListTechniques:
    def test_list_techniques_includes_description_and_schema(
        self, client, db_session, auth_headers
    ):
        response = client.get("/api/v1/analysis/techniques", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0
        for tech in data:
            assert "name" in tech
            assert "supported_types" in tech
            assert "description" in tech
            assert "parameters_schema" in tech


class TestGpuTechniqueConfig:
    def test_deepfake_similarity_not_in_gpu_techniques(self):
        from core.gpu_inference import ML_GPU_TECHNIQUES

        assert "deepfake_similarity" not in ML_GPU_TECHNIQUES

    def test_synthetic_image_detection_is_gpu(self):
        from core.gpu_inference import ML_GPU_TECHNIQUES

        assert "synthetic_image_detection" in ML_GPU_TECHNIQUES


class TestCeleryTaskRoutes:
    def test_cpu_task_has_10_minute_timeout(self):
        from app.celery_app import celery_app

        annotations = celery_app.conf.task_annotations
        assert annotations["tasks.analysis_tasks.run_forensic_analysis_cpu"]["time_limit"] == 600
        assert annotations["tasks.analysis_tasks.run_forensic_analysis_cpu"]["soft_time_limit"] == 540

    def test_gpu_task_has_1_hour_timeout(self):
        from app.celery_app import celery_app

        annotations = celery_app.conf.task_annotations
        assert annotations["tasks.analysis_tasks.run_forensic_analysis_gpu"]["time_limit"] == 3600
        assert annotations["tasks.analysis_tasks.run_forensic_analysis_gpu"]["soft_time_limit"] == 3300
