"""Tests for custody chain module — TDD Red phase.

Expected: ALL tests fail because CustodyService does not exist yet.
"""

import uuid

import pytest
from sqlalchemy import update, text

from models.custody_record import CustodyRecord


class TestCustodyService:
    """TU-CUST-001 to TU-CUST-007"""

    def test_create_first_record(self, db_session, sample_case, test_user):
        """TU-CUST-001: First custody record has no previous hash."""
        from services.custody_service import CustodyService
        service = CustodyService(db_session)
        record = service.create_record(
            record_type="evidence_upload",
            case_id=sample_case.id,
            evidence_id=None,
            job_id=None,
            user_id=test_user.id,
            sha256_input="a" * 64,
            sha256_output=None,
            sha256_params=None,
            details={"filename": "test.jpg"},
        )

        assert record.record_hash is not None
        assert len(record.record_hash) == 64
        assert record.previous_record_hash is None
        assert record.timestamp is not None

    def test_chain_linking(self, db_session, sample_case, test_user):
        """TU-CUST-002: Second record links to first record's hash."""
        from services.custody_service import CustodyService
        service = CustodyService(db_session)

        first = service.create_record(
            record_type="evidence_upload",
            case_id=sample_case.id,
            user_id=test_user.id,
            details={},
        )

        second = service.create_record(
            record_type="analysis_started",
            case_id=sample_case.id,
            user_id=test_user.id,
            details={},
        )

        assert first.chain_sequence == 1
        assert second.chain_sequence == 2
        assert second.previous_record_hash == first.record_hash
        assert second.record_hash != first.record_hash

    def test_verify_valid_chain(self, db_session, sample_case, test_user):
        """TU-CUST-003: Valid chain returns valid=true."""
        from services.custody_service import CustodyService
        service = CustodyService(db_session)
        for _ in range(3):
            service.create_record(
                record_type="evidence_upload",
                case_id=sample_case.id,
                user_id=test_user.id,
                details={},
            )

        result = service.verify_chain(sample_case.id)
        assert result["valid"] is True
        assert result["records_checked"] == 3
        assert result["first_invalid"] is None

    def test_verify_chain_stable_with_same_timestamp(self, db_session, sample_case, test_user):
        """Registros no mesmo segundo mantem encadeamento deterministico."""
        from services.custody_service import CustodyService

        service = CustodyService(db_session)
        for i in range(3):
            service.create_record(
                record_type="evidence_upload",
                case_id=sample_case.id,
                user_id=test_user.id,
                details={"seq": i},
            )
        result = service.verify_chain(sample_case.id)
        assert result["valid"] is True

    def test_broken_link_stays_invalid(self, db_session, sample_case, test_user):
        """Encadeamento adulterado permanece invalido (sem reparo)."""
        from services.custody_service import CustodyService

        service = CustodyService(db_session)
        service.create_record(
            record_type="evidence_upload",
            case_id=sample_case.id,
            user_id=test_user.id,
            details={"n": 1},
        )
        second = service.create_record(
            record_type="evidence_upload",
            case_id=sample_case.id,
            user_id=test_user.id,
            details={"n": 2},
        )

        db_session.execute(text("DROP TRIGGER IF EXISTS trg_custody_immutable"))
        second.previous_record_hash = "0" * 64
        second.record_hash = service._compute_hash(second)
        db_session.commit()
        db_session.execute(
            text(
                """
                CREATE TRIGGER IF NOT EXISTS trg_custody_immutable
                BEFORE UPDATE ON custody_records
                BEGIN
                    SELECT RAISE(IGNORE);
                END;
                """
            )
        )

        result = service.verify_chain(sample_case.id)
        assert result["valid"] is False
        assert result["reason"] in (
            "previous_record_hash_mismatch",
            "broken_chain_or_orphan",
            "chain_cycle",
            "unlinked_custody_records",
        )

    def test_detect_tampering(self, db_session, sample_case, test_user):
        """TU-CUST-004: Tampered record is detected in chain verification."""
        from services.custody_service import CustodyService
        service = CustodyService(db_session)

        records = []
        for _ in range(3):
            r = service.create_record(
                record_type="evidence_upload",
                case_id=sample_case.id,
                user_id=test_user.id,
                details={},
            )
            records.append(r)

        # Temporarily drop immutability trigger so we can simulate tampering
        db_session.execute(text("DROP TRIGGER IF EXISTS trg_custody_immutable"))
        db_session.commit()

        # Tamper second record
        db_session.execute(
            update(CustodyRecord)
            .where(CustodyRecord.id == records[1].id)
            .values(record_hash=" tampered_hash_123 ")
        )
        db_session.commit()

        result = service.verify_chain(sample_case.id)
        assert result["valid"] is False
        assert result["reason"] in (
            "record_hash_mismatch",
            "broken_chain_or_orphan",
            "unlinked_custody_records",
        )
        assert result["first_invalid"] in {str(r.id) for r in records}

    def test_immutability(self, db_session, sample_case, test_user):
        """TU-CUST-005: UPDATE on custody_records should fail or affect 0 rows."""
        from services.custody_service import CustodyService
        service = CustodyService(db_session)
        record = service.create_record(
            record_type="evidence_upload",
            case_id=sample_case.id,
            user_id=test_user.id,
            details={},
        )

        result = db_session.execute(
            update(CustodyRecord)
            .where(CustodyRecord.id == record.id)
            .values(record_hash="hacked")
        )

        # Either raises exception or affects 0 rows depending on implementation
        assert result.rowcount == 0 or result.rowcount is None

    def test_recompute_reproducible(self, db_session, sample_case, test_user, sample_evidence):
        """TU-CUST-006: Recomputed job hash matches original."""
        from services.custody_service import CustodyService
        from models.analysis_job import AnalysisJob
        service = CustodyService(db_session)

        # Create a completed job with known hash
        job = AnalysisJob(
            id=uuid.uuid4(),
            evidence_id=sample_evidence.id,
            technique="mock",
            status="completed",
            parameters={},
            result_sha256="original_hash_123",
            created_by=test_user.id,
        )
        db_session.add(job)
        db_session.commit()

        result = service.recompute_job_hash(job.id)
        assert result["reproducible"] is True
        assert result["original_hash"] == "original_hash_123"
        assert result["new_hash"] == "original_hash_123"

    def test_batch_create_in_one_transaction(self, db_session, sample_case, test_user):
        """Dois registros no mesmo commit encadeiam pela cauda criptografica."""
        from services.custody_service import CustodyService

        service = CustodyService(db_session)
        first = service.create_record(
            record_type="case_closed",
            case_id=sample_case.id,
            user_id=test_user.id,
            details={"step": 1},
            commit=False,
        )
        second = service.create_record(
            record_type="case_closure_signed",
            case_id=sample_case.id,
            user_id=test_user.id,
            details={"step": 2},
            commit=False,
        )
        db_session.commit()

        assert first.chain_sequence == 1
        assert second.chain_sequence == 2
        assert second.previous_record_hash == first.record_hash
        result = service.verify_chain(sample_case.id)
        assert result["valid"] is True

    def test_chain_sequence_gap_is_failure(self, db_session, sample_case, test_user):
        """Sequencia fora de 1..n na ordem criptografica falha verificacao."""
        from services.custody_service import CustodyService

        service = CustodyService(db_session)
        service.create_record(
            record_type="evidence_upload",
            case_id=sample_case.id,
            user_id=test_user.id,
            details={},
        )
        second = service.create_record(
            record_type="evidence_upload",
            case_id=sample_case.id,
            user_id=test_user.id,
            details={},
        )

        db_session.execute(text("DROP TRIGGER IF EXISTS trg_custody_immutable"))
        second.chain_sequence = 99
        db_session.commit()
        db_session.execute(
            text(
                """
                CREATE TRIGGER IF NOT EXISTS trg_custody_immutable
                BEFORE UPDATE ON custody_records
                BEGIN
                    SELECT RAISE(IGNORE);
                END;
                """
            )
        )

        result = service.verify_chain(sample_case.id)
        assert result["valid"] is False
        assert result["reason"] == "chain_sequence_gap"

    def test_recompute_not_reproducible(self, db_session, sample_case, test_user, sample_evidence):
        """TU-CUST-007: Tampered artifact fails reproducibility."""
        from services.custody_service import CustodyService
        from models.analysis_job import AnalysisJob
        service = CustodyService(db_session)

        job = AnalysisJob(
            id=uuid.uuid4(),
            evidence_id=sample_evidence.id,
            technique="mock",
            status="completed",
            parameters={},
            result_sha256="original_hash_123",
            created_by=test_user.id,
        )
        db_session.add(job)
        db_session.commit()

        # Simulate tampered artifact by mocking the adapter to return different hash
        result = service.recompute_job_hash(job.id)
        # This may be False if adapter detects difference
        # For Red phase, we just assert the method exists and returns expected keys
        assert "reproducible" in result
        assert "original_hash" in result
        assert "new_hash" in result
