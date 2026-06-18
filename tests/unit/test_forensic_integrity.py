"""Tests for forensic integrity verification."""

import uuid
from pathlib import Path

import pytest

from models.evidence import Evidence
from services.custody_service import CustodyService
from services.forensic_integrity_service import ForensicIntegrityService


class TestForensicIntegrity:
    def test_valid_case_passes(self, db_session, sample_case, test_user, sample_evidence, tmp_path):
        path = tmp_path / "ev.jpg"
        path.write_bytes(b"test-image-data")
        sample_evidence.file_path = str(path)
        sample_evidence.sha256 = __import__("hashlib").sha256(path.read_bytes()).hexdigest()
        db_session.commit()

        CustodyService(db_session).create_record(
            record_type="evidence_upload",
            case_id=sample_case.id,
            evidence_id=sample_evidence.id,
            user_id=test_user.id,
            sha256_input=sample_evidence.sha256,
            details={"original_filename": sample_evidence.original_filename},
        )

        report = ForensicIntegrityService(db_session).verify_case_forensic_integrity(
            sample_case.id
        )
        assert report["chain"]["valid"] is True
        assert report["valid"] is True

    def test_hash_mismatch_detected(
        self, db_session, sample_case, test_user, sample_evidence, tmp_path
    ):
        path = tmp_path / "ev.jpg"
        path.write_bytes(b"original")
        import hashlib

        sample_evidence.file_path = str(path)
        sample_evidence.sha256 = hashlib.sha256(b"wrong").hexdigest()
        db_session.commit()

        report = ForensicIntegrityService(db_session).verify_case_forensic_integrity(
            sample_case.id
        )
        assert report["valid"] is False
        assert len(report["files"]["hash_mismatch"]) >= 1
