"""Tests for jobs module — TDD Red phase.

Expected: ALL tests fail because JobService, analysis endpoints, and Celery tasks do not exist yet.
"""

import json
import uuid
from pathlib import Path

import pytest
from sqlalchemy.orm import Session


class TestJobService:
    """TU-JOB-001 to TU-JOB-008"""

    def test_submit_job_valid(self, db_session, sample_evidence, test_user):
        """TU-JOB-001: Submit job with valid evidence and technique."""
        from services.job_service import JobService
        service = JobService(db_session)

        job = service.submit_job(
            evidence_id=sample_evidence.id,
            technique="mock_technique",
            parameters={"threshold": 0.5},
            user_id=test_user.id,
        )

        assert job.id is not None
        assert job.status == "pending"
        assert job.technique == "mock_technique"
        assert job.parameters == {"threshold": 0.5}
        assert job.evidence_id == sample_evidence.id
        assert job.created_by == test_user.id

    def test_submit_job_evidence_not_found(self, db_session, test_user):
        """TU-JOB-002: Submit job with non-existent evidence raises 404."""
        from services.job_service import JobService
        service = JobService(db_session)

        with pytest.raises(Exception) as exc_info:
            service.submit_job(
                evidence_id=uuid.uuid4(),
                technique="mock_technique",
                parameters={},
                user_id=test_user.id,
            )

        assert "404" in str(exc_info.value) or "not found" in str(exc_info.value).lower()

    def test_submit_job_invalid_technique(self, db_session, sample_evidence, test_user):
        """TU-JOB-003: Submit job with technique not in registry raises 422."""
        from services.job_service import JobService
        service = JobService(db_session)

        with pytest.raises(Exception) as exc_info:
            service.submit_job(
                evidence_id=sample_evidence.id,
                technique="nonexistent_technique_xyz",
                parameters={},
                user_id=test_user.id,
            )

        assert "422" in str(exc_info.value) or "invalid" in str(exc_info.value).lower()

    def test_submit_job_invalid_parameters(self, db_session, sample_evidence, test_user):
        """TU-JOB-004: Submit job with invalid parameters raises 422."""
        from services.job_service import JobService
        service = JobService(db_session)

        with pytest.raises(Exception) as exc_info:
            service.submit_job(
                evidence_id=sample_evidence.id,
                technique="mock_technique",
                parameters={"invalid_param": 123},
                user_id=test_user.id,
            )

        assert "422" in str(exc_info.value) or "invalid" in str(exc_info.value).lower()

    def test_get_job_by_id(self, db_session, sample_evidence, test_user):
        """TU-JOB-005: Get job by ID returns job metadata."""
        from services.job_service import JobService
        service = JobService(db_session)

        job = service.submit_job(
            evidence_id=sample_evidence.id,
            technique="mock_technique",
            parameters={},
            user_id=test_user.id,
        )

        found = service.get_job(job.id)
        assert found.id == job.id
        assert found.status == "pending"

    def test_get_job_not_found(self, db_session):
        """TU-JOB-006: Get non-existent job raises 404."""
        from services.job_service import JobService
        service = JobService(db_session)

        with pytest.raises(Exception) as exc_info:
            service.get_job(uuid.uuid4())

        assert "404" in str(exc_info.value) or "not found" in str(exc_info.value).lower()

    def test_list_techniques(self, db_session):
        """TU-JOB-007: List available techniques from plugin registry."""
        from services.job_service import JobService
        service = JobService(db_session)

        techniques = service.list_techniques()
        assert isinstance(techniques, list)
        # At minimum, our mock plugin should be registered
        assert len(techniques) >= 1
        assert all("name" in t for t in techniques)
        assert all("supported_types" in t for t in techniques)

    def test_run_job_task_updates_status(self, db_session, sample_evidence, test_user):
        """TU-JOB-008: Running a job task updates status to completed."""
        from services.job_service import JobService
        service = JobService(db_session)

        job = service.submit_job(
            evidence_id=sample_evidence.id,
            technique="mock_technique",
            parameters={},
            user_id=test_user.id,
        )

        # Simulate task execution
        service.run_job(job.id)

        updated = service.get_job(job.id)
        assert updated.status == "completed"
        assert updated.completed_at is not None
        assert updated.artifact_sha256 is None
        assert isinstance(updated.runtime_manifest, dict)
        assert updated.runtime_manifest.get("kind") == "job_execution_receipt"
        assert updated.runtime_manifest.get("execution_digest")
        assert len(updated.runtime_manifest.get("execution_digest", "")) == 64
        assert updated.determinism_profile == "strict"

        result_json = Path(updated.result_path) / "result.json"
        assert result_json.is_file()
        payload = json.loads(result_json.read_text(encoding="utf-8"))
        assert payload.get("preview") is True
        assert payload.get("promoted") is False
        assert "job_receipt" in payload
        assert "reproducibility_manifest.json" not in [p.name for p in Path(updated.result_path).iterdir()]

    def test_reproduce_job_matches_itself(self, db_session, sample_evidence, test_user, tmp_path):
        """Re-running a mock job in temp dir should match its artifact_sha256."""
        from services.job_service import JobService

        evidence_file = tmp_path / "mock.jpg"
        evidence_file.write_bytes(b"\xff\xd8\xff mock jpeg")
        sample_evidence.file_path = str(evidence_file)
        db_session.commit()

        service = JobService(db_session)
        job = service.submit_job(
            evidence_id=sample_evidence.id,
            technique="mock_technique",
            parameters={},
            user_id=test_user.id,
        )
        service.run_job(job.id)
        completed = service.get_job(job.id)
        report = service.reproduce_job(job.id)
        assert report["status"] == "MATCH"
        assert report["artifact_match"] is True
        assert report.get("comparison_mode") == "execution_receipt"
        assert report["reproduced_artifact_sha256"] == completed.runtime_manifest.get(
            "execution_digest"
        )
