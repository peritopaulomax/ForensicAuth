"""Case sharing endpoints."""

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from models.user import User
from models.case import Case
from models.user import User
from services.case_share_service import CaseShareService

router = APIRouter()


class SharedCaseResponse(BaseModel):
    id: str
    protocol_number: str
    inquiry_number: Optional[str] = None
    process_number: Optional[str] = None
    title: str
    description: Optional[str] = None
    status: str
    created_by: str
    assigned_to: Optional[str] = None
    created_at: str
    updated_at: str
    evidence_count: int = 0
    is_shared: bool = True


def _case_to_shared_response(case: Case) -> SharedCaseResponse:
    evidence_count = sum(
        1 for e in (case.evidences or []) if getattr(e, "deleted_at", None) is None
    )
    return SharedCaseResponse(
        id=str(case.id),
        protocol_number=case.protocol_number,
        inquiry_number=case.inquiry_number,
        process_number=case.process_number,
        title=case.title,
        description=case.description,
        status=case.status,
        created_by=str(case.created_by),
        assigned_to=str(case.assigned_to) if case.assigned_to else None,
        created_at=case.created_at.isoformat() if case.created_at else "",
        updated_at=case.updated_at.isoformat() if case.updated_at else "",
        evidence_count=evidence_count,
    )


class CreateShareRequest(BaseModel):
    user_id: str = Field(..., description="UUID do usuario destino")
    role: str = Field(default="viewer", pattern="^(viewer|editor)$")


class ShareResponse(BaseModel):
    id: str
    case_id: str
    shared_with_user_id: str
    shared_with_username: Optional[str] = None
    role: str
    shared_by: str
    created_at: str


@router.post(
    "/cases/{case_id}/shares",
    status_code=status.HTTP_201_CREATED,
    response_model=ShareResponse,
)
def create_share(
    case_id: uuid.UUID,
    request: CreateShareRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    share = CaseShareService(db).share_case(
        case_id,
        uuid.UUID(request.user_id),
        request.role,
        current_user,
    )
    target = db.query(User).filter(User.id == share.shared_with_user_id).first()
    return ShareResponse(
        id=str(share.id),
        case_id=str(share.case_id),
        shared_with_user_id=str(share.shared_with_user_id),
        shared_with_username=target.username if target else None,
        role=share.role,
        shared_by=str(share.shared_by),
        created_at=share.created_at.isoformat() if share.created_at else "",
    )


@router.get("/cases/{case_id}/shares", response_model=List[ShareResponse])
def list_shares(
    case_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    shares = CaseShareService(db).list_shares(case_id, current_user)
    result = []
    for share in shares:
        target = db.query(User).filter(User.id == share.shared_with_user_id).first()
        result.append(
            ShareResponse(
                id=str(share.id),
                case_id=str(share.case_id),
                shared_with_user_id=str(share.shared_with_user_id),
                shared_with_username=target.username if target else None,
                role=share.role,
                shared_by=str(share.shared_by),
                created_at=share.created_at.isoformat() if share.created_at else "",
            )
        )
    return result


@router.delete("/cases/{case_id}/shares/{share_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_share(
    case_id: uuid.UUID,
    share_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    CaseShareService(db).revoke_share(case_id, share_id, current_user)


@router.get("/users/for-sharing")
def list_users_for_sharing(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Active users available as share targets (excludes self)."""
    users = (
        db.query(User)
        .filter(User.is_active, User.id != current_user.id, User.role.in_(["perito", "admin"]))
        .order_by(User.username.asc())
        .all()
    )
    return [
        {"id": str(u.id), "username": u.username, "email": u.email, "role": u.role}
        for u in users
    ]


@router.get("/cases/shared-with-me", response_model=List[SharedCaseResponse])
def list_shared_with_me(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cases = CaseShareService(db).list_shared_with_me(current_user)
    return [_case_to_shared_response(c) for c in cases]
