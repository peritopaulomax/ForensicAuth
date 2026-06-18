"""Persistencia da chave Ed25519 de desenvolvimento (sem re-assinatura automatica)."""

import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import services.custody_signing_service as signing_module
from models.custody_record import CustodyRecord
from services.custody_service import CustodyService, _allow_custody_record_updates
from services.custody_signing_service import _load_or_create_dev_key, dev_signing_key_path
from services.forensic_integrity_service import ForensicIntegrityService


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
