"""Tests for case visibility by creator / assignee."""

import uuid

import pytest

from models.case import Case
from services.case_access import cases_query_for_user, get_accessible_case


@pytest.fixture
def other_user(db_session):
    import bcrypt
    from models.user import User

    user = User(
        id=uuid.uuid4(),
        username="outro.perito",
        email="outro@pf.gov.br",
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
def case_by_test_user(db_session, test_user):
    case = Case(
        protocol_number="CASO-A-001",
        title="Caso do test_user",
        created_by=test_user.id,
        status="aberto",
    )
    db_session.add(case)
    db_session.commit()
    db_session.refresh(case)
    return case


@pytest.fixture
def case_by_other_user(db_session, other_user):
    case = Case(
        protocol_number="CASO-B-001",
        title="Caso de outro usuario",
        created_by=other_user.id,
        status="aberto",
    )
    db_session.add(case)
    db_session.commit()
    db_session.refresh(case)
    return case


class TestCaseAccess:
    def test_user_sees_only_own_cases(
        self, db_session, test_user, case_by_test_user, case_by_other_user
    ):
        cases = cases_query_for_user(db_session, test_user).all()
        ids = {c.id for c in cases}
        assert case_by_test_user.id in ids
        assert case_by_other_user.id not in ids

    def test_cannot_access_other_users_case(
        self, db_session, test_user, case_by_other_user
    ):
        with pytest.raises(Exception):
            get_accessible_case(db_session, case_by_other_user.id, test_user)

    def test_admin_sees_all_cases(
        self, db_session, test_admin, other_user, case_by_other_user
    ):
        own = Case(
            protocol_number="CASO-ADMIN-001",
            title="Caso admin",
            created_by=test_admin.id,
            status="aberto",
        )
        db_session.add(own)
        db_session.commit()

        cases = cases_query_for_user(db_session, test_admin).all()
        ids = {c.id for c in cases}
        assert own.id in ids
        assert case_by_other_user.id in ids
