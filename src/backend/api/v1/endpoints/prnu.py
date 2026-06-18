"""PRNU fingerprint management endpoints (per case)."""

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from models.user import User
from services import prnu_fingerprint_service as fp_service

router = APIRouter()


class CreateFingerprintRequest(BaseModel):
    evidence_ids: List[str] = Field(..., min_length=1)
    label: Optional[str] = Field(None, max_length=120)
    group_label: Optional[str] = Field(None, max_length=120)
    sigma: float = Field(default=3.0, ge=0.5, le=10.0)


@router.get("/cases/{case_id}/prnu/fingerprints")
def list_case_fingerprints(
    case_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return fp_service.list_fingerprints(db, case_id, user)


@router.post("/cases/{case_id}/prnu/fingerprints", status_code=201)
def create_case_fingerprint(
    case_id: uuid.UUID,
    body: CreateFingerprintRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ev_ids = [uuid.UUID(e) for e in body.evidence_ids]
    return fp_service.create_fingerprint(
        db,
        case_id,
        ev_ids,
        body.label or "",
        body.sigma,
        user,
        group_label=body.group_label,
    )
