"""Integration tests for case sharing API."""

import uuid

import pytest
from jose import jwt

from app.config import get_settings
from models.case import Case


@pytest.fixture
def user_b(db_session):
    import bcrypt
    from models.user import User

    user = User(
        id=uuid.uuid4(),
        username="perito_b",
        email="b@pf.gov.br",
        hashed_password=bcrypt.hashpw("Senha1234".encode(), bcrypt.gensalt()).decode(),
        role="perito",
        is_active=True,
        password_set=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def auth_b(user_b):
    settings = get_settings()
    token = jwt.encode(
        {"sub": str(user_b.id), "role": user_b.role},
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )
    return {"Authorization": f"Bearer {token}"}


class TestCaseSharesAPI:
    def test_share_and_list_shared(
        self, client, db_session, sample_case, test_user, user_b, auth_headers, auth_b
    ):
        r = client.post(
            f"/api/v1/cases/{sample_case.id}/shares",
            json={"user_id": str(user_b.id), "role": "editor"},
            headers=auth_headers,
        )
        assert r.status_code == 201

        r2 = client.get("/api/v1/cases/shared-with-me", headers=auth_b)
        assert r2.status_code == 200
        ids = [c["id"] for c in r2.json()]
        assert str(sample_case.id) in ids

    def test_third_party_forbidden(
        self, client, sample_case, db_session, auth_headers
    ):
        import bcrypt
        from models.user import User

        other = User(
            id=uuid.uuid4(),
            username="perito_c",
            email="c@pf.gov.br",
            hashed_password=bcrypt.hashpw("Senha1234".encode(), bcrypt.gensalt()).decode(),
            role="perito",
            is_active=True,
            password_set=True,
        )
        db_session.add(other)
        db_session.commit()
        settings = get_settings()
        token = jwt.encode(
            {"sub": str(other.id), "role": other.role},
            settings.SECRET_KEY,
            algorithm=settings.ALGORITHM,
        )
        headers = {"Authorization": f"Bearer {token}"}
        r = client.get(f"/api/v1/cases/{sample_case.id}", headers=headers)
        assert r.status_code == 404
