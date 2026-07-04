"""Phase 2 domain validation tests.

Tests for divergences BE-05/FJ-06, BE-06, BE-11 and BE-04/BE-12:
- Technique compatibility vs evidence media type.
- Reference uploads require case edit permission / closed case blocked.
- Evidence upload service rejects closed cases.
- Update case no longer accepts status field.
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
from services.evidence_service import EvidenceService, EvidenceUploadError
from services.job_service import JobService


def _auth_headers_for(user, settings):
    token = jwt.encode(
        {"sub": str(user.id), "role": user.role},
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def shared_viewer(db_session):
    import bcrypt

    user = User(
        id=uuid.uuid4(),
        username="viewer02",
        email="viewer02@pf.gov.br",
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
def closed_case(db_session, sample_case):
    sample_case.status = "fechado"
    db_session.commit()
    db_session.refresh(sample_case)
    return sample_case


class TestTechniqueCompatibility:
    def test_submit_job_incompatible_technique_returns_422(
        self, db_session, sample_case, sample_evidence, test_user
    ):
        """Audio technique on image evidence must be rejected."""
        service = JobService(db_session)
        with pytest.raises(Exception) as exc:
            service.submit_job(
                evidence_id=sample_evidence.id,
                technique="audio_enf",
                parameters={},
                user_id=test_user.id,
            )
        assert exc.value.status_code == 422
        assert "nao suporta" in exc.value.detail.lower()

    def test_submit_job_compatible_technique_succeeds(
        self, db_session, sample_case, sample_evidence, test_user
    ):
        """Image technique on image evidence must be accepted."""
        service = JobService(db_session)
        job = service.submit_job(
            evidence_id=sample_evidence.id,
            technique="ela",
            parameters={},
            user_id=test_user.id,
        )
        assert job.status == "pending"


class TestReferenceUploads:
    def test_reference_upload_closed_case_blocked(
        self, client, db_session, closed_case, test_user
    ):
        from app.config import get_settings

        headers = _auth_headers_for(test_user, get_settings())
        response = client.post(
            "/api/v1/evidences/reference-upload",
            data={"case_id": str(closed_case.id), "group_label": "grupo1"},
            files={"file": ("ref.jpg", io.BytesIO(b"\xff\xd8\xff\xe0" + b"\x00" * 100), "image/jpeg")},
            headers=headers,
        )
        assert response.status_code == 409


class TestEvidenceUploadService:
    def test_upload_evidence_closed_case_blocked(
        self, db_session, closed_case, test_user
    ):
        service = EvidenceService(db_session)
        file_obj = io.BytesIO(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

        with pytest.raises(Exception) as exc:
            service.upload_evidence(
                case_id=closed_case.id,
                filename="photo.jpg",
                mime_type="image/jpeg",
                file_obj=file_obj,
                uploaded_by=test_user.id,
            )
        assert exc.value.status_code == 409


class TestUpdateCaseStatus:
    def test_update_case_status_field_rejected(
        self, client, db_session, sample_case, test_user
    ):
        from app.config import get_settings

        headers = _auth_headers_for(test_user, get_settings())
        response = client.put(
            f"/api/v1/cases/{sample_case.id}",
            json={"status": "fechado"},
            headers=headers,
        )
        assert response.status_code == 422
