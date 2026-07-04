"""Phase 1 security/custody validations.

Tests for critical divergences BE-01, BE-02, BE-03 and FJ-04:
- Submit analysis job on closed/pending-closure case is blocked.
- Submit analysis job by shared viewer is blocked.
- Delete evidence on closed/pending-closure case is blocked.
- Delete evidence by shared viewer is blocked.
- Update case by shared viewer is blocked.
"""

import io
import uuid

import pytest
from fastapi.testclient import TestClient
from jose import jwt

from models.case import Case
from models.case_share import CaseShare
from models.evidence import Evidence
from models.user import User


@pytest.fixture
def other_user(db_session):
    import bcrypt

    user = User(
        id=uuid.uuid4(),
        username="perito02",
        email="perito02@pf.gov.br",
        hashed_password=bcrypt.hashpw("Senha1234".encode(), bcrypt.gensalt()).decode(),
        role="perito",
        is_active=True,
        password_set=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def shared_viewer(db_session):
    import bcrypt

    user = User(
        id=uuid.uuid4(),
        username="viewer01",
        email="viewer01@pf.gov.br",
        hashed_password=bcrypt.hashpw("Senha1234".encode(), bcrypt.gensalt()).decode(),
        role="perito",
        is_active=True,
        password_set=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def shared_case(db_session, sample_case, shared_viewer, test_user):
    share = CaseShare(
        id=uuid.uuid4(),
        case_id=sample_case.id,
        shared_with_user_id=shared_viewer.id,
        role="viewer",
        shared_by=test_user.id,
    )
    db_session.add(share)
    db_session.commit()
    db_session.refresh(sample_case)
    return sample_case


@pytest.fixture
def shared_evidence(db_session, shared_case, test_user):
    evidence = Evidence(
        id=uuid.uuid4(),
        case_id=shared_case.id,
        filename="teste.jpg",
        original_filename="foto_original.jpg",
        file_path="/uploads/teste.jpg",
        file_size=1024,
        file_type="imagem",
        mime_type="image/jpeg",
        sha256="a" * 64,
        uploaded_by=test_user.id,
    )
    db_session.add(evidence)
    db_session.commit()
    db_session.refresh(evidence)
    return evidence


def _auth_headers_for(user, settings):
    token = jwt.encode(
        {"sub": str(user.id), "role": user.role},
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )
    return {"Authorization": f"Bearer {token}"}


class TestSubmitJobSecurity:
    def test_submit_job_closed_case_blocked(
        self, client, db_session, sample_case, sample_evidence, test_user, auth_headers
    ):
        sample_case.status = "fechado"
        db_session.commit()

        response = client.post(
            "/api/v1/analysis",
            json={"evidence_id": str(sample_evidence.id), "technique": "ela"},
            headers=auth_headers,
        )
        assert response.status_code == 409

    def test_submit_job_pending_closure_blocked(
        self, client, db_session, sample_case, sample_evidence, test_user, auth_headers
    ):
        sample_case.status = "fechamento_pendente"
        db_session.commit()

        response = client.post(
            "/api/v1/analysis",
            json={"evidence_id": str(sample_evidence.id), "technique": "ela"},
            headers=auth_headers,
        )
        assert response.status_code == 409

    def test_submit_job_by_shared_viewer_blocked(
        self, client, db_session, shared_case, shared_evidence, shared_viewer
    ):
        from app.config import get_settings

        headers = _auth_headers_for(shared_viewer, get_settings())
        response = client.post(
            "/api/v1/analysis",
            json={"evidence_id": str(shared_evidence.id), "technique": "ela"},
            headers=headers,
        )
        assert response.status_code == 403


class TestDeleteEvidenceSecurity:
    def test_delete_evidence_closed_case_blocked(
        self, client, db_session, sample_case, sample_evidence, test_user, auth_headers
    ):
        sample_case.status = "fechado"
        db_session.commit()

        response = client.delete(
            f"/api/v1/evidences/{sample_evidence.id}",
            headers=auth_headers,
        )
        assert response.status_code == 409

    def test_delete_evidence_by_shared_viewer_blocked(
        self, client, db_session, shared_case, shared_evidence, shared_viewer
    ):
        from app.config import get_settings

        headers = _auth_headers_for(shared_viewer, get_settings())
        response = client.delete(
            f"/api/v1/evidences/{shared_evidence.id}",
            headers=headers,
        )
        assert response.status_code == 403


class TestUpdateCaseSecurity:
    def test_update_case_by_shared_viewer_blocked(
        self, client, db_session, shared_case, shared_viewer
    ):
        from app.config import get_settings

        headers = _auth_headers_for(shared_viewer, get_settings())
        response = client.put(
            f"/api/v1/cases/{shared_case.id}",
            json={"title": "Tentativa de alteracao"},
            headers=headers,
        )
        assert response.status_code == 403


class TestProductionSecrets:
    def test_production_rejects_default_secret_key(self, monkeypatch):
        from app.config import Settings

        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
        monkeypatch.setenv("SECRET_KEY", "change-me-in-production-forensicauth-2026")
        monkeypatch.setenv("CUSTODY_SIGNING_PRIVATE_KEY", "dummy-key")

        with pytest.raises(ValueError, match="SECRET_KEY"):
            Settings()

    def test_production_rejects_missing_custody_key(self, monkeypatch):
        from app.config import Settings

        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
        monkeypatch.setenv("SECRET_KEY", "strong-secret-key-at-least-32-chars-long")
        monkeypatch.setenv("CUSTODY_SIGNING_PRIVATE_KEY", "")

        with pytest.raises(ValueError, match="CUSTODY_SIGNING_PRIVATE_KEY"):
            Settings()

    def test_development_allows_default_secret_key(self, monkeypatch):
        from app.config import Settings

        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
        monkeypatch.setenv("SECRET_KEY", "change-me-in-production-forensicauth-2026")

        settings = Settings()
        assert settings.SECRET_KEY == "change-me-in-production-forensicauth-2026"
