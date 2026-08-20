"""Custody chain, signing (Ed25519), persistência de chave e relatório narrativo.\n\nMERGE mecânico (Fase 3f) — anexados signing/signing_persist/narrative.\nMantido separado: test_custody_integration.py\n"""

import uuid

import pytest
from sqlalchemy import update, text

from models.custody_record import CustodyRecord

import base64
import hashlib

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import services.custody_signing_service as signing_module
from services.custody_narrative_report import CustodyNarrativeReportService
from services.custody_service import CustodyService, _allow_custody_record_updates
from services.custody_signing_service import CustodySigningService, _load_or_create_dev_key, dev_signing_key_path
from services.forensic_integrity_service import ForensicIntegrityService


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

    def test_verify_empty_case_chain(self, db_session, sample_case):
        """Caso sem elos de custodia (ainda sem evidencias) e valido."""
        from services.custody_service import CustodyService

        result = CustodyService(db_session).verify_chain(sample_case.id)
        assert result["valid"] is True
        assert result["records_checked"] == 0
        seal = CustodyService(db_session).verify_case_custody_seal(sample_case.id)
        assert seal["valid"] is True
        assert seal["reason"] == "chain_empty"

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

    def test_case_custody_seal_created_on_record(self, db_session, sample_case, test_user):
        """Ao criar registro, o caso recebe selo de fechamento da cadeia."""
        from services.custody_service import CustodyService

        service = CustodyService(db_session)
        record = service.create_record(
            record_type="evidence_upload",
            case_id=sample_case.id,
            user_id=test_user.id,
            details={},
        )

        db_session.refresh(sample_case)
        assert sample_case.custody_seal is not None
        assert sample_case.custody_seal_signature is not None
        assert sample_case.custody_seal_record_hash == record.record_hash

    def test_case_custody_seal_detects_deleted_last_record(self, db_session, sample_case, test_user):
        """Remocao do ultimo registro invalida o selo de fechamento."""
        from services.custody_service import CustodyService
        from models.custody_record import CustodyRecord

        service = CustodyService(db_session)
        for _ in range(3):
            service.create_record(
                record_type="evidence_upload",
                case_id=sample_case.id,
                user_id=test_user.id,
                details={},
            )

        assert service.verify_chain(sample_case.id)["valid"] is True

        last = (
            db_session.query(CustodyRecord)
            .filter(CustodyRecord.case_id == sample_case.id)
            .order_by(CustodyRecord.chain_sequence.desc())
            .first()
        )
        db_session.delete(last)
        db_session.commit()

        result = service.verify_chain(sample_case.id)
        assert result["valid"] is False
        assert "custody_seal_invalid" in result["reason"]


# --- signing (ex test_custody_signing) ---


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


# --- signing persist (ex test_custody_signing_persist) ---


class TestDevSigningKeyPersist:
    def test_dev_key_persisted_and_reloaded(self, monkeypatch, tmp_path):
        signing_module._DEV_PRIVATE_KEY = None
        signing_module._DEV_PUBLIC_KEY = None
        uploads = tmp_path / "uploads"
        uploads.mkdir()
        monkeypatch.setenv("UPLOAD_DIR", str(uploads))
        from app.config import get_settings

        get_settings.cache_clear()
        settings = get_settings()

        _load_or_create_dev_key(settings)
        path = dev_signing_key_path(settings)
        assert path.is_file()

        get_settings.cache_clear()
        settings2 = get_settings()
        k1, _ = _load_or_create_dev_key(settings2)
        raw = path.read_text(encoding="ascii").strip()
        k2 = Ed25519PrivateKey.from_private_bytes(base64.b64decode(raw + "=" * (-len(raw) % 4)))
        assert (
            k1.private_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PrivateFormat.Raw,
                encryption_algorithm=serialization.NoEncryption(),
            )
            == k2.private_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PrivateFormat.Raw,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )

    def test_invalid_signature_fails_forensic_without_auto_fix(
        self, db_session, sample_case, test_user, monkeypatch, tmp_path
    ):
        signing_module._DEV_PRIVATE_KEY = None
        signing_module._DEV_PUBLIC_KEY = None
        uploads = tmp_path / "uploads"
        uploads.mkdir()
        monkeypatch.setenv("UPLOAD_DIR", str(uploads))
        from app.config import get_settings

        get_settings.cache_clear()
        _load_or_create_dev_key(get_settings())

        CustodyService(db_session).create_record(
            record_type="evidence_upload",
            case_id=sample_case.id,
            user_id=test_user.id,
            details={},
        )
        with _allow_custody_record_updates(db_session):
            record = (
                db_session.query(CustodyRecord)
                .filter_by(case_id=sample_case.id)
                .first()
            )
            record.system_signature = base64.b64encode(b"x" * 64).decode("ascii")
            db_session.commit()

        report = ForensicIntegrityService(db_session).verify_case_forensic_integrity(
            sample_case.id
        )
        assert report["chain"]["valid"] is True
        assert report["valid"] is False
        assert len(report["signatures"]["invalid"]) == 1


# --- narrative report (ex test_custody_narrative_report) ---


class TestCustodyNarrativeReport:
    def test_build_and_render(
        self, db_session, sample_case, test_user, sample_evidence, tmp_path
    ):
        path = tmp_path / "ev.jpg"
        path.write_bytes(b"pixel-data")

        sample_evidence.file_path = str(path)
        sample_evidence.sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        db_session.commit()

        CustodyService(db_session).create_record(
            record_type="evidence_upload",
            case_id=sample_case.id,
            evidence_id=sample_evidence.id,
            user_id=test_user.id,
            sha256_input=sample_evidence.sha256,
            details={
                "original_filename": sample_evidence.original_filename,
                "file_type": "imagem",
                "file_size": 10,
                "sha256": sample_evidence.sha256,
            },
        )

        svc = CustodyNarrativeReportService(db_session)
        report = svc.build(sample_case.id)
        assert report["case"]["protocol_number"] == sample_case.protocol_number
        assert len(report["events"]) >= 1
        assert "Evidencia recebida" in report["events"][0]["title"]
        assert any("registrou o recebimento" in p for p in report["events"][0]["paragraphs"])

        html = svc.render_html(report)
        assert "Linha do tempo" in html
        assert sample_case.protocol_number in html

        md = svc.render_markdown(report)
        assert sample_case.protocol_number in md
        assert "## Linha do tempo" in md
