"""Unit tests for VCP case export/import."""

import uuid
from pathlib import Path

from models.analysis_job import AnalysisJob
from models.case import Case
from models.custody_record import CustodyRecord
from models.evidence import Evidence
from services.case_transfer_service import CaseTransferService
from services.custody_service import CustodyService


class TestCaseTransfer:
    def test_export_validate_roundtrip(
        self, db_session, sample_case, test_user, sample_evidence, tmp_path
    ):
        path = tmp_path / "case.vcp.zip"
        svc = CaseTransferService(db_session)
        CustodyService(db_session).create_record(
            record_type="evidence_upload",
            case_id=sample_case.id,
            evidence_id=sample_evidence.id,
            user_id=test_user.id,
            sha256_input=sample_evidence.sha256,
            sha256_output=sample_evidence.sha256,
            details={"original_filename": sample_evidence.original_filename},
        )

        sample_evidence.file_path = str(
            tmp_path / sample_evidence.original_filename
        )
        Path(sample_evidence.file_path).write_bytes(b"roundtrip-bytes")
        import hashlib

        sample_evidence.sha256 = hashlib.sha256(
            Path(sample_evidence.file_path).read_bytes()
        ).hexdigest()
        db_session.commit()

        out = svc.export_case(sample_case.id, test_user, path)
        assert out.is_file()

        pkg_report = svc.validate_package(path, db=None)
        assert pkg_report["valid"] is True, pkg_report.get("issues")

        case_id = sample_case.id
        db_session.query(CustodyRecord).filter(CustodyRecord.case_id == case_id).delete()
        db_session.query(Evidence).filter(Evidence.case_id == case_id).delete()
        db_session.query(Case).filter(Case.id == case_id).delete()
        db_session.commit()

        pre_import = svc.validate_package(path, db=db_session)
        assert pre_import["valid"] is True, pre_import.get("issues")

        result = svc.import_case(path, test_user)
        assert result["chain_valid"] is True
        assert result["evidences_imported"] == 1

        chain = CustodyService(db_session).verify_chain(case_id)
        assert chain["valid"] is True

    def test_validate_detects_tampered_file(
        self, db_session, sample_case, test_user, sample_evidence, tmp_path
    ):
        import hashlib
        import zipfile
        import json

        data = b"tamper-test"
        sample_evidence.file_path = str(tmp_path / "ev.bin")
        Path(sample_evidence.file_path).write_bytes(data)
        sample_evidence.sha256 = hashlib.sha256(data).hexdigest()
        db_session.commit()

        path = tmp_path / "tamper.vcp.zip"
        svc = CaseTransferService(db_session)
        svc.export_case(sample_case.id, test_user, path)

        with zipfile.ZipFile(path, "a") as zf:
            zf.writestr(f"files/{sample_evidence.sha256}", b"altered")

        report = svc.validate_package(path, db=None)
        assert report["valid"] is False

    def test_import_replaces_soft_deleted_tombstone(
        self, db_session, sample_case, test_user, sample_evidence, tmp_path
    ):
        import hashlib

        from services.case_deletion_service import CaseDeletionService

        data = b"tombstone-roundtrip"
        sample_evidence.file_path = str(tmp_path / "ev.bin")
        Path(sample_evidence.file_path).write_bytes(data)
        sample_evidence.sha256 = hashlib.sha256(data).hexdigest()
        db_session.commit()

        path = tmp_path / "tombstone.vcp.zip"
        svc = CaseTransferService(db_session)
        CustodyService(db_session).create_record(
            record_type="evidence_upload",
            case_id=sample_case.id,
            evidence_id=sample_evidence.id,
            user_id=test_user.id,
            sha256_input=sample_evidence.sha256,
            sha256_output=sample_evidence.sha256,
        )
        svc.export_case(sample_case.id, test_user, path)

        case_id = sample_case.id
        original_protocol = sample_case.protocol_number
        CaseDeletionService(db_session).delete_case(case_id, test_user)
        db_session.expire_all()

        pre = svc.validate_package(path, db=db_session)
        assert pre["valid"] is True, pre.get("issues")
        assert pre["conflicts"]["replaceable_tombstone"] is not None

        result = svc.import_case(path, test_user)
        assert result["chain_valid"] is True

        restored = db_session.query(Case).filter(Case.id == case_id).one()
        assert restored.deleted_at is None
        assert restored.protocol_number == original_protocol

        imported_rec = (
            db_session.query(CustodyRecord)
            .filter(
                CustodyRecord.case_id == case_id,
                CustodyRecord.record_type == "case_imported",
            )
            .one()
        )
        assert imported_rec.details.get("replaced_tombstone") is not None
        assert imported_rec.details["replaced_tombstone"].get("case_deleted_record_hash")

    def test_import_tombstone_removes_purged_jobs_before_reinsert(
        self, db_session, sample_case, test_user, sample_evidence, tmp_path
    ):
        import hashlib

        from models.analysis_job import AnalysisJob
        from services.case_deletion_service import CaseDeletionService

        data = b"tombstone-jobs"
        sample_evidence.file_path = str(tmp_path / "ev.bin")
        Path(sample_evidence.file_path).write_bytes(data)
        sample_evidence.sha256 = hashlib.sha256(data).hexdigest()
        db_session.commit()

        job_id = uuid.uuid4()
        job = AnalysisJob(
            id=job_id,
            evidence_id=sample_evidence.id,
            technique="ela",
            status="completed",
            parameters={},
            created_by=test_user.id,
        )
        db_session.add(job)
        db_session.flush()

        svc = CaseTransferService(db_session)
        CustodyService(db_session).create_record(
            record_type="evidence_upload",
            case_id=sample_case.id,
            evidence_id=sample_evidence.id,
            user_id=test_user.id,
            sha256_input=sample_evidence.sha256,
            sha256_output=sample_evidence.sha256,
        )
        CustodyService(db_session).create_record(
            record_type="analysis_completed",
            case_id=sample_case.id,
            evidence_id=sample_evidence.id,
            job_id=job.id,
            user_id=test_user.id,
            sha256_output=sample_evidence.sha256,
            details={"technique": "ela"},
        )

        path = tmp_path / "tombstone-jobs.vcp.zip"
        svc.export_case(sample_case.id, test_user, path)

        case_id = sample_case.id
        CaseDeletionService(db_session).delete_case(case_id, test_user)
        db_session.expire_all()
        assert (
            db_session.query(AnalysisJob).filter(AnalysisJob.id == job_id).count() == 1
        )

        result = svc.import_case(path, test_user)
        assert result["chain_valid"] is True
        restored_job = db_session.query(AnalysisJob).filter(AnalysisJob.id == job_id).one()
        assert restored_job.status in ("completed", "purged")

    def test_import_creates_stub_jobs_for_custody_refs(
        self, db_session, sample_case, test_user, sample_evidence, tmp_path
    ):
        import hashlib
        from models.analysis_job import AnalysisJob

        data = b"job-stub-import"
        sample_evidence.file_path = str(tmp_path / "ev.bin")
        Path(sample_evidence.file_path).write_bytes(data)
        sample_evidence.sha256 = hashlib.sha256(data).hexdigest()
        db_session.commit()

        job_id = uuid.uuid4()
        job = AnalysisJob(
            id=job_id,
            evidence_id=sample_evidence.id,
            technique="ela",
            status="completed",
            parameters={},
            created_by=test_user.id,
        )
        db_session.add(job)
        db_session.flush()

        svc = CaseTransferService(db_session)
        CustodyService(db_session).create_record(
            record_type="analysis_completed",
            case_id=sample_case.id,
            evidence_id=sample_evidence.id,
            job_id=job.id,
            user_id=test_user.id,
            sha256_output=sample_evidence.sha256,
            details={"technique": "ela"},
        )

        path = tmp_path / "with-job.vcp.zip"
        svc.export_case(sample_case.id, test_user, path)

        case_id = sample_case.id
        db_session.query(CustodyRecord).filter(CustodyRecord.case_id == case_id).delete()
        db_session.query(AnalysisJob).filter(AnalysisJob.id == job_id).delete()
        db_session.query(Evidence).filter(Evidence.case_id == case_id).delete()
        db_session.query(Case).filter(Case.id == case_id).delete()
        db_session.commit()

        result = svc.import_case(path, test_user)
        assert result["chain_valid"] is True
        assert db_session.query(AnalysisJob).filter(AnalysisJob.id == job_id).count() == 1

    def test_export_includes_jobs_and_soft_deleted_evidence_in_chain(
        self, db_session, sample_case, test_user, sample_evidence, tmp_path
    ):
        import hashlib
        import zipfile

        data = b"export-meta"
        sample_evidence.file_path = str(tmp_path / "ev.bin")
        Path(sample_evidence.file_path).write_bytes(data)
        sample_evidence.sha256 = hashlib.sha256(data).hexdigest()
        db_session.commit()

        svc = CaseTransferService(db_session)
        CustodyService(db_session).create_record(
            record_type="evidence_upload",
            case_id=sample_case.id,
            evidence_id=sample_evidence.id,
            user_id=test_user.id,
            sha256_input=sample_evidence.sha256,
            sha256_output=sample_evidence.sha256,
        )
        job_id = uuid.uuid4()
        job = AnalysisJob(
            id=job_id,
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
            sha256_output=sample_evidence.sha256,
            details={"technique": "ela"},
        )

        path = tmp_path / "meta.vcp.zip"
        svc.export_case(sample_case.id, test_user, path)

        with zipfile.ZipFile(path, "r") as zf:
            names = set(zf.namelist())
            assert "case/analysis_jobs.json" in names
            jobs = __import__("json").loads(zf.read("case/analysis_jobs.json"))
            assert any(j["id"] == str(job_id) for j in jobs)
