"""Tests for case sharing and access control."""

import uuid

import pytest

from models.case import Case
from models.case_share import CaseShare
from models.user import User
from services.case_access import cases_query_for_user, get_case_access_level
from services.case_share_service import CaseShareService


@pytest.fixture
def test_user_b(db_session):
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


class TestCaseShares:
    def test_query_includes_active_share(self, db_session, sample_case, test_user, test_user_b):
        share = CaseShare(
            id=uuid.uuid4(),
            case_id=sample_case.id,
            shared_with_user_id=test_user_b.id,
            role="viewer",
            shared_by=test_user.id,
        )
        db_session.add(share)
        db_session.commit()

        ids = [c.id for c in cases_query_for_user(db_session, test_user_b).all()]
        assert sample_case.id in ids

    def test_revoked_share_excluded(self, db_session, sample_case, test_user, test_user_b):
        from app.utils import utc_now

        share = CaseShare(
            id=uuid.uuid4(),
            case_id=sample_case.id,
            shared_with_user_id=test_user_b.id,
            role="viewer",
            shared_by=test_user.id,
            revoked_at=utc_now(),
        )
        db_session.add(share)
        db_session.commit()

        ids = [c.id for c in cases_query_for_user(db_session, test_user_b).all()]
        assert sample_case.id not in ids

    def test_share_creates_custody_record(
        self, db_session, sample_case, test_user, test_user_b
    ):
        from models.custody_record import CustodyRecord

        CaseShareService(db_session).share_case(
            sample_case.id, test_user_b.id, "editor", test_user
        )
        rec = (
            db_session.query(CustodyRecord)
            .filter(
                CustodyRecord.case_id == sample_case.id,
                CustodyRecord.record_type == "case_shared",
            )
            .first()
        )
        assert rec is not None

    def test_access_level_shared_editor(
        self, db_session, sample_case, test_user, test_user_b
    ):
        share = CaseShare(
            id=uuid.uuid4(),
            case_id=sample_case.id,
            shared_with_user_id=test_user_b.id,
            role="editor",
            shared_by=test_user.id,
        )
        db_session.add(share)
        db_session.commit()
        level = get_case_access_level(db_session, sample_case, test_user_b)
        assert level == "shared_editor"
