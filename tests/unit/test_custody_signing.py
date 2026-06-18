"""Tests for Ed25519 custody record signing."""

from services.custody_service import CustodyService
from services.custody_signing_service import CustodySigningService


class TestCustodySigning:
    def test_new_record_has_valid_signature(self, db_session, sample_case, test_user):
        service = CustodyService(db_session)
        record = service.create_record(
            record_type="evidence_upload",
            case_id=sample_case.id,
            user_id=test_user.id,
            details={"test": True},
        )
        assert record.system_signature
        assert record.signing_key_id
        signing = CustodySigningService()
        assert signing.verify_digest_hex(
            record.record_hash,
            record.system_signature,
            record.signing_key_id,
        )

    def test_verify_record_includes_signature(self, db_session, sample_case, test_user):
        service = CustodyService(db_session)
        record = service.create_record(
            record_type="evidence_upload",
            case_id=sample_case.id,
            user_id=test_user.id,
            details={},
        )
        result = service.verify_record(record.id)
        assert result["signature_valid"] is True
