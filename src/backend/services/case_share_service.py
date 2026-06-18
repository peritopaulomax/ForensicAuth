"""Case sharing service."""

import uuid
from typing import List

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from models.case import Case
from models.case_share import CaseShare
from models.user import User
from services.case_access import (
    assert_can_share_case,
    assert_case_not_closed,
    get_accessible_case,
)
from services.custody_service import CustodyService


class CaseShareService:
    def __init__(self, db: Session):
        self.db = db

    def _active_share(
        self, case_id: uuid.UUID, target_user_id: uuid.UUID
    ) -> CaseShare | None:
        return (
            self.db.query(CaseShare)
            .filter(
                CaseShare.case_id == case_id,
                CaseShare.shared_with_user_id == target_user_id,
                CaseShare.revoked_at.is_(None),
            )
            .first()
        )

    def share_case(
        self,
        case_id: uuid.UUID,
        target_user_id: uuid.UUID,
        role: str,
        current_user: User,
    ) -> CaseShare:
        if role not in ("viewer", "editor"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="role deve ser viewer ou editor",
            )
        case = get_accessible_case(self.db, case_id, current_user)
        assert_can_share_case(self.db, case, current_user)
        assert_case_not_closed(case)

        if target_user_id == case.created_by:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Nao e possivel compartilhar com o criador do caso",
            )
        if target_user_id == current_user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Nao e possivel compartilhar consigo mesmo",
            )

        target = self.db.query(User).filter(User.id == target_user_id, User.is_active).first()
        if not target:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Usuario destino nao encontrado",
            )

        existing = self._active_share(case_id, target_user_id)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Caso ja compartilhado com este usuario",
            )

        share = CaseShare(
            id=uuid.uuid4(),
            case_id=case_id,
            shared_with_user_id=target_user_id,
            role=role,
            shared_by=current_user.id,
        )
        self.db.add(share)
        self.db.flush()

        CustodyService(self.db).create_record(
            record_type="case_shared",
            case_id=case_id,
            user_id=current_user.id,
            details={
                "share_id": str(share.id),
                "shared_with_user_id": str(target_user_id),
                "shared_with_username": target.username,
                "role": role,
            },
            commit=False,
        )
        self.db.commit()
        self.db.refresh(share)
        return share

    def list_shares(self, case_id: uuid.UUID, current_user: User) -> List[CaseShare]:
        get_accessible_case(self.db, case_id, current_user)
        return (
            self.db.query(CaseShare)
            .filter(CaseShare.case_id == case_id, CaseShare.revoked_at.is_(None))
            .order_by(CaseShare.created_at.desc())
            .all()
        )

    def revoke_share(
        self, case_id: uuid.UUID, share_id: uuid.UUID, current_user: User
    ) -> None:
        case = get_accessible_case(self.db, case_id, current_user)
        assert_can_share_case(self.db, case, current_user)

        share = (
            self.db.query(CaseShare)
            .filter(
                CaseShare.id == share_id,
                CaseShare.case_id == case_id,
                CaseShare.revoked_at.is_(None),
            )
            .first()
        )
        if not share:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Compartilhamento nao encontrado",
            )

        from app.utils import utc_now

        share.revoked_at = utc_now()
        target = self.db.query(User).filter(User.id == share.shared_with_user_id).first()

        CustodyService(self.db).create_record(
            record_type="case_unshared",
            case_id=case_id,
            user_id=current_user.id,
            details={
                "share_id": str(share.id),
                "shared_with_user_id": str(share.shared_with_user_id),
                "shared_with_username": target.username if target else None,
                "role": share.role,
            },
            commit=False,
        )
        self.db.commit()

    def list_shared_with_me(self, current_user: User) -> List[Case]:
        share_case_ids = [
            row[0]
            for row in self.db.query(CaseShare.case_id)
            .filter(
                CaseShare.shared_with_user_id == current_user.id,
                CaseShare.revoked_at.is_(None),
            )
            .all()
        ]
        if not share_case_ids:
            return []
        return (
            self.db.query(Case)
            .filter(Case.id.in_(share_case_ids), Case.deleted_at.is_(None))
            .order_by(Case.updated_at.desc())
            .all()
        )
