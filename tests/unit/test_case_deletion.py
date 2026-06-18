"""Exclusao de caso com preservacao da cadeia de custodia."""

import uuid
from pathlib import Path

import pytest

from models.analysis_job import AnalysisJob
from models.custody_record import CustodyRecord
from models.evidence import Evidence
from services.case_deletion_service import CaseDeletionError, CaseDeletionService


class TestCaseDeletion:
    def test_delete_case_removes_files_keeps_custody(
        self, db_session, sample_case, test_user, sample_evidence, tmp_path, monkeypatch
    ):
        from app.config import get_settings

        settings = get_settings()
        upload = Path(sample_evidence.file_path)
        upload.parent.mkdir(parents=True, exist_ok=True)
        upload.write_bytes(b"evidence-bytes")

        deriv_root = Path(settings.DERIVATIVES_DIR) / str(sample_case.id)
        deriv_root.mkdir(parents=True, exist_ok=True)
        deriv_file = deriv_root / "test.npy"
        deriv_file.write_bytes(b"npy")

        job_id = uuid.uuid4()
        result_dir = Path(settings.RESULTS_DIR) / str(job_id)
        result_dir.mkdir(parents=True, exist_ok=True)
        (result_dir / "out.png").write_bytes(b"png")
        job = AnalysisJob(
            id=job_id,
            evidence_id=sample_evidence.id,
            technique="ela",
            status="completed",
            parameters={},
            result_path=str(result_dir),
            created_by=test_user.id,
        )
        db_session.add(job)

        custody_before = (
            db_session.query(CustodyRecord)
            .filter(CustodyRecord.case_id == sample_case.id)
            .count()
        )
        db_session.commit()

        service = CaseDeletionService(db_session)
        result = service.delete_case(sample_case.id, test_user)

        assert result["deleted"] is True
        assert not upload.exists()
        assert not deriv_file.exists()
        assert not result_dir.exists()

        db_session.refresh(sample_case)
        assert sample_case.deleted_at is not None
        assert sample_case.protocol_number.endswith(str(sample_case.id).replace("-", "")[:8])

        ev = db_session.query(Evidence).filter(Evidence.case_id == sample_case.id).one()
        assert ev.deleted_at is not None
        assert ev.extra_metadata.get("purged_with_case") is True
        job_row = (
            db_session.query(AnalysisJob)
            .filter(AnalysisJob.id == job_id)
            .one()
        )
        assert job_row.status == "purged"
        assert job_row.result_path is None
        assert job_row.parameters.get("purged_with_case") is True

        custody_after = (
            db_session.query(CustodyRecord)
            .filter(CustodyRecord.case_id == sample_case.id)
            .count()
        )
        assert custody_after == custody_before + 1
        deleted_rec = (
            db_session.query(CustodyRecord)
            .filter(
                CustodyRecord.case_id == sample_case.id,
                CustodyRecord.record_type == "case_deleted",
            )
            .one()
        )
        assert deleted_rec.details.get("snapshot", {}).get("evidence_count") >= 1
        assert deleted_rec.details.get("case_excluded") is True

    def test_delete_already_deleted_fails(self, db_session, sample_case, test_user):
        service = CaseDeletionService(db_session)
        service.delete_case(sample_case.id, test_user)
        with pytest.raises(CaseDeletionError, match="ja foi excluido"):
            service.delete_case(sample_case.id, test_user)

    def test_delete_long_protocol_fits_varchar50(self, db_session, test_user):
        from models.case import Case
        from services.case_deletion_service import tombstone_protocol_number

        case = Case(
            id=uuid.uuid4(),
            protocol_number="A" * 50,
            title="Long protocol",
            created_by=test_user.id,
            status="aberto",
        )
        db_session.add(case)
        db_session.commit()
        tomb = tombstone_protocol_number(case.protocol_number, case.id)
        assert len(tomb) <= 50
        CaseDeletionService(db_session).delete_case(case.id, test_user)
        db_session.refresh(case)
        assert len(case.protocol_number) <= 50

    def test_list_hides_deleted_case(self, db_session, sample_case, test_user):
        from services.case_access import cases_query_for_user

        CaseDeletionService(db_session).delete_case(sample_case.id, test_user)
        visible = cases_query_for_user(db_session, test_user).all()
        assert all(c.id != sample_case.id for c in visible)

    def test_delete_case_with_custody_job_refs(
        self, db_session, sample_case, test_user, sample_evidence
    ):
        """Registros imutaveis mantem job_id — exclusao nao pode apagar AnalysisJob."""
        from services.custody_service import CustodyService

        job = AnalysisJob(
            id=uuid.uuid4(),
            evidence_id=sample_evidence.id,
            technique="ela",
            status="completed",
            parameters={},
            created_by=test_user.id,
        )
        db_session.add(job)
        db_session.flush()

        CustodyService(db_session).create_record(
            record_type="analysis_completed",
            case_id=sample_case.id,
            evidence_id=sample_evidence.id,
            job_id=job.id,
            user_id=test_user.id,
            sha256_output="abc123",
        )
        db_session.commit()

        CaseDeletionService(db_session).delete_case(sample_case.id, test_user)

        db_session.refresh(job)
        assert job.status == "purged"
        assert (
            db_session.query(CustodyRecord)
            .filter(CustodyRecord.job_id == job.id)
            .count()
            == 1
        )
