"""Tests for case close/reopen lifecycle (bilateral signatures)."""

import uuid

import pytest
from fastapi import HTTPException

from models.case_share import CaseShare
from models.user import User
from services.case_lifecycle_service import CaseLifecycleService, ForensicManifestBuilder


@pytest.fixture
def second_perito(db_session):
    user = User(
        id=uuid.uuid4(),
        username="perito.dois",
        email="perito2@test.com",
        hashed_password="x",
        role="perito",
        is_active=True,
        password_set=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


class TestCaseLifecycle:
    def test_manifest_hash_stable(self, db_session, sample_case):
        b = ForensicManifestBuilder()
        m1 = b.build(db_session, sample_case)
        m2 = b.build(db_session, sample_case)
        assert m1["manifest_sha256"] == m2["manifest_sha256"]

    def test_single_owner_closes_immediately(
        self, db_session, sample_case, test_user
    ):
        svc = CaseLifecycleService(db_session)
        closure, status = svc.close_case(sample_case.id, test_user)
        db_session.refresh(sample_case)
        assert sample_case.status == "fechado"
        assert status["fully_closed"] is True
        assert closure.system_signature

    def test_close_blocks_when_already_closed(
        self, db_session, sample_case, test_user
    ):
        svc = CaseLifecycleService(db_session)
        svc.close_case(sample_case.id, test_user)
        with pytest.raises(HTTPException) as exc:
            svc.close_case(sample_case.id, test_user)
        assert exc.value.status_code == 409

    def test_bilateral_pending_until_all_sign(
        self, db_session, sample_case, test_user, second_perito
    ):
        share = CaseShare(
            id=uuid.uuid4(),
            case_id=sample_case.id,
            shared_with_user_id=second_perito.id,
            role="editor",
            shared_by=test_user.id,
        )
        db_session.add(share)
        db_session.commit()

        svc = CaseLifecycleService(db_session)
        _, status1 = svc.close_case(sample_case.id, test_user)
        db_session.refresh(sample_case)
        assert sample_case.status == "fechamento_pendente"
        assert status1["fully_closed"] is False
        assert status1["pending_count"] == 1

        _, status2 = svc.close_case(sample_case.id, second_perito)
        db_session.refresh(sample_case)
        assert sample_case.status == "fechado"
        assert status2["fully_closed"] is True

    def test_icp_returns_501(self, db_session, sample_case, test_user):
        svc = CaseLifecycleService(db_session)
        with pytest.raises(HTTPException) as exc:
            svc.close_case(sample_case.id, test_user, signature_mode="icp_brasil")
        assert exc.value.status_code == 501

    def test_reopen_from_pending(self, db_session, sample_case, test_user, second_perito):
        share = CaseShare(
            id=uuid.uuid4(),
            case_id=sample_case.id,
            shared_with_user_id=second_perito.id,
            role="editor",
            shared_by=test_user.id,
        )
        db_session.add(share)
        db_session.commit()

        svc = CaseLifecycleService(db_session)
        svc.close_case(sample_case.id, test_user)
        case = svc.reopen_case(sample_case.id, test_user)
        assert case.status == "aberto"
