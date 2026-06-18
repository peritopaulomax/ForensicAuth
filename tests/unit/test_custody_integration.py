"""Integration tests for custody chain — upload, audit, permissions."""

import io
import uuid

import pytest
from fastapi.testclient import TestClient

from models.case import Case
from models.custody_record import CustodyRecord


@pytest.fixture
def assignee_perito(db_session):
    import bcrypt
    from models.user import User

    user = User(
        id=uuid.uuid4(),
        username="perito02",
        email="perito02@pf.gov.br",
        hashed_password=bcrypt.hashpw(b"Senha1234", bcrypt.gensalt()).decode(),
        password_set=True,
        role="perito",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def assigned_case(db_session, test_user, assignee_perito):
    case = Case(
        protocol_number="CASO-ASSIGN-001",
        title="Caso designado",
        created_by=test_user.id,
        assigned_to=assignee_perito.id,
        status="aberto",
    )
    db_session.add(case)
    db_session.commit()
    db_session.refresh(case)
    return case


@pytest.fixture
def assignee_auth_headers(assignee_perito):
    from jose import jwt
    from app.config import get_settings

    settings = get_settings()
    token = jwt.encode(
        {"sub": str(assignee_perito.id), "role": assignee_perito.role},
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )
    return {"Authorization": f"Bearer {token}"}


class TestCustodyIntegration:
    """TI-CUST-001, TI-CUST-002"""

    def test_upload_creates_custody_record(
        self, client, db_session, sample_case, auth_headers
    ):
        """TI-CUST-001: Upload generates evidence_upload custody record."""
        file_content = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 100
        response = client.post(
            "/api/v1/evidences/upload",
            data={"case_id": str(sample_case.id)},
            files={"file": ("photo.jpg", io.BytesIO(file_content), "image/jpeg")},
            headers=auth_headers,
        )
        assert response.status_code == 201
        evidence = response.json()
        assert len(evidence["sha256"]) == 64

        records = (
            db_session.query(CustodyRecord)
            .filter(
                CustodyRecord.case_id == sample_case.id,
                CustodyRecord.record_type == "evidence_upload",
            )
            .all()
        )
        assert len(records) == 1
        assert records[0].sha256_input == evidence["sha256"]
        assert str(records[0].evidence_id) == evidence["id"]

        from services.custody_service import CustodyService

        verify = CustodyService(db_session).verify_chain(sample_case.id)
        assert verify["valid"] is True

    def test_delete_creates_custody_record(
        self, client, db_session, sample_case, auth_headers
    ):
        file_content = b"\xff\xd8\xff\xe0\x00\x10JFIF delete test"
        upload = client.post(
            "/api/v1/evidences/upload",
            data={"case_id": str(sample_case.id)},
            files={"file": ("del.jpg", io.BytesIO(file_content), "image/jpeg")},
            headers=auth_headers,
        )
        evidence_id = upload.json()["id"]
        sha = upload.json()["sha256"]

        response = client.delete(
            f"/api/v1/evidences/{evidence_id}",
            headers=auth_headers,
        )
        assert response.status_code == 204

        deleted_records = (
            db_session.query(CustodyRecord)
            .filter(CustodyRecord.record_type == "evidence_deleted")
            .all()
        )
        assert len(deleted_records) == 1
        assert deleted_records[0].sha256_input == sha
        assert deleted_records[0].details.get("evidence_id") == evidence_id

    def test_audit_permissions(
        self,
        client,
        db_session,
        test_user,
        test_admin,
        other_user_fixture,
        sample_case,
        assigned_case,
        auth_headers,
        admin_auth_headers,
        assignee_auth_headers,
    ):
        """TI-CUST-002: Audit access by role."""
        # Seed a custody record on sample_case (owned by test_user)
        from services.custody_service import CustodyService

        CustodyService(db_session).create_record(
            record_type="evidence_upload",
            case_id=sample_case.id,
            user_id=test_user.id,
            details={},
        )

        # Perito own case → 200
        r = client.get(
            "/api/v1/audit",
            params={"case_id": str(sample_case.id)},
            headers=auth_headers,
        )
        assert r.status_code == 200
        assert len(r.json()) >= 1

        # Admin any case → 200
        r = client.get(
            "/api/v1/audit",
            params={"case_id": str(sample_case.id)},
            headers=admin_auth_headers,
        )
        assert r.status_code == 200

        # Perito atribuido ao caso → 200
        CustodyService(db_session).create_record(
            record_type="evidence_upload",
            case_id=assigned_case.id,
            user_id=test_user.id,
            details={},
        )
        r = client.get(
            "/api/v1/audit",
            params={"case_id": str(assigned_case.id)},
            headers=assignee_auth_headers,
        )
        assert r.status_code == 200

        # Perito nao atribuido ao caso → 403
        r = client.get(
            "/api/v1/audit",
            params={"case_id": str(sample_case.id)},
            headers=assignee_auth_headers,
        )
        assert r.status_code in (403, 404)


@pytest.fixture
def other_user_fixture(db_session):
    import bcrypt
    from models.user import User

    user = User(
        id=uuid.uuid4(),
        username="outro.perito2",
        email="outro2@pf.gov.br",
        hashed_password=bcrypt.hashpw(b"Senha1234", bcrypt.gensalt()).decode(),
        password_set=True,
        role="perito",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user
