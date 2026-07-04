"""Case endpoints — CRUD for forensic cases."""

import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from models.case import Case
from models.user import User
from services.case_access import (
    assert_can_create_case,
    assert_can_edit_case,
    cases_query_for_user,
    get_accessible_case,
)
from services.case_deletion_service import CaseDeletionError, CaseDeletionService
from services.case_lifecycle_service import CaseLifecycleService

router = APIRouter()


class CreateCaseRequest(BaseModel):
    protocol_number: str = Field(..., min_length=1, description="Numero do protocolo")
    inquiry_number: Optional[str] = Field(None, description="Numero do inquerito")
    process_number: Optional[str] = Field(None, description="Numero do processo")
    title: str = Field(..., min_length=1, description="Titulo/nome do caso")
    description: Optional[str] = Field(None, description="Descricao/detalhes")
    assigned_to: Optional[str] = Field(None, description="ID do usuario atribuido")


class UpdateCaseRequest(BaseModel):
    model_config = {"extra": "forbid"}

    protocol_number: Optional[str] = Field(None, min_length=1)
    inquiry_number: Optional[str] = None
    process_number: Optional[str] = None
    title: Optional[str] = Field(None, min_length=1)
    description: Optional[str] = None
    assigned_to: Optional[str] = None


class CaseResponse(BaseModel):
    id: str
    protocol_number: str
    inquiry_number: Optional[str]
    process_number: Optional[str]
    title: str
    description: Optional[str]
    status: str
    storage_mode: str = "va"
    created_by: str
    assigned_to: Optional[str]
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class CaseDetailResponse(CaseResponse):
    evidence_count: int = 0
    is_shared: bool = False


class CloseCaseRequest(BaseModel):
    signature_mode: str = Field(default="system", pattern="^(system|icp_brasil)$")
    note: Optional[str] = None


class ClosureResponse(BaseModel):
    id: str
    case_id: str
    closure_sequence: int
    manifest_sha256: str
    signature_mode: str
    signed_by: str
    signed_at: str
    system_signature: Optional[str] = None


class ClosureSignerStatus(BaseModel):
    user_id: str
    username: Optional[str] = None
    role: str
    signed: bool
    is_current_user: bool


class ClosureStatusResponse(BaseModel):
    case_status: str
    fully_closed: bool
    closure_pending: bool
    active_closure_id: Optional[str] = None
    required_signers: List[ClosureSignerStatus]
    pending_signers: List[ClosureSignerStatus]
    pending_count: int
    all_signed: bool
    current_user_must_sign: bool
    current_user_can_initiate: bool
    message: str


class CloseCaseResultResponse(BaseModel):
    closure: ClosureResponse
    case_status: str
    fully_closed: bool
    closure_status: ClosureStatusResponse


def _case_to_detail(case: Case) -> CaseDetailResponse:
    storage_mode = getattr(case, "storage_mode", "va") or "va"
    evidence_count = sum(
        1 for e in (case.evidences or []) if getattr(e, "deleted_at", None) is None
    )
    return CaseDetailResponse(
        id=str(case.id),
        protocol_number=case.protocol_number,
        inquiry_number=case.inquiry_number,
        process_number=case.process_number,
        title=case.title,
        description=case.description,
        status=case.status,
        storage_mode=storage_mode,
        created_by=str(case.created_by),
        assigned_to=str(case.assigned_to) if case.assigned_to else None,
        created_at=case.created_at.isoformat() if case.created_at else "",
        updated_at=case.updated_at.isoformat() if case.updated_at else "",
        evidence_count=evidence_count,
    )


@router.post("/cases", status_code=status.HTTP_201_CREATED, response_model=CaseResponse)
def create_case(
    request: CreateCaseRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new forensic case."""
    assert_can_create_case(current_user)
    case = Case(
        id=uuid.uuid4(),
        protocol_number=request.protocol_number,
        inquiry_number=request.inquiry_number,
        process_number=request.process_number,
        title=request.title,
        description=request.description,
        created_by=current_user.id,
        assigned_to=uuid.UUID(request.assigned_to) if request.assigned_to else None,
        status="aberto",
    )
    db.add(case)
    db.commit()
    db.refresh(case)
    return CaseResponse(
        id=str(case.id),
        protocol_number=case.protocol_number,
        inquiry_number=case.inquiry_number,
        process_number=case.process_number,
        title=case.title,
        description=case.description,
        status=case.status,
        storage_mode=getattr(case, "storage_mode", "va") or "va",
        created_by=str(case.created_by),
        assigned_to=str(case.assigned_to) if case.assigned_to else None,
        created_at=case.created_at.isoformat() if case.created_at else "",
        updated_at=case.updated_at.isoformat() if case.updated_at else "",
    )


@router.get("/cases", response_model=List[CaseDetailResponse])
def list_cases(
    scope: Optional[str] = Query(None, pattern="^(mine|shared|all)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List cases visible to the current user."""
    effective_scope = scope or "all"
    cases = (
        cases_query_for_user(db, current_user, scope=effective_scope)
        .order_by(Case.created_at.desc())
        .all()
    )
    from services.case_access import get_case_access_level

    result = []
    for case in cases:
        detail = _case_to_detail(case)
        level = get_case_access_level(db, case, current_user)
        detail.is_shared = level in ("shared_editor", "shared_viewer")
        result.append(detail)
    return result


@router.get("/cases/{case_id}", response_model=CaseDetailResponse)
def get_case(
    case_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a single case by ID."""
    case = get_accessible_case(db, case_id, current_user)
    from services.case_access import get_case_access_level

    detail = _case_to_detail(case)
    level = get_case_access_level(db, case, current_user)
    detail.is_shared = level in ("shared_editor", "shared_viewer")
    return detail


@router.put("/cases/{case_id}", response_model=CaseResponse)
def update_case(
    case_id: uuid.UUID,
    request: UpdateCaseRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update an existing case."""
    case = get_accessible_case(db, case_id, current_user)
    assert_can_edit_case(db, case, current_user)

    if request.protocol_number is not None:
        case.protocol_number = request.protocol_number
    if request.inquiry_number is not None:
        case.inquiry_number = request.inquiry_number
    if request.process_number is not None:
        case.process_number = request.process_number
    if request.title is not None:
        case.title = request.title
    if request.description is not None:
        case.description = request.description
    if request.assigned_to is not None:
        case.assigned_to = uuid.UUID(request.assigned_to)

    db.commit()
    db.refresh(case)
    return CaseResponse(
        id=str(case.id),
        protocol_number=case.protocol_number,
        inquiry_number=case.inquiry_number,
        process_number=case.process_number,
        title=case.title,
        description=case.description,
        status=case.status,
        storage_mode=getattr(case, "storage_mode", "va") or "va",
        created_by=str(case.created_by),
        assigned_to=str(case.assigned_to) if case.assigned_to else None,
        created_at=case.created_at.isoformat() if case.created_at else "",
        updated_at=case.updated_at.isoformat() if case.updated_at else "",
    )


@router.delete("/cases/{case_id}", status_code=status.HTTP_200_OK)
def delete_case(
    case_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Exclui caso: remove arquivos e registros operacionais; preserva cadeia de custodia."""
    try:
        result = CaseDeletionService(db).delete_case(case_id, current_user)
    except CaseDeletionError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except HTTPException:
        raise
    except IntegrityError as exc:
        db.rollback()
        detail = str(getattr(exc, "orig", exc))
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Nao foi possivel excluir o caso (conflito de integridade). "
                "Reinicie o backend e tente novamente."
                + (f" Detalhe: {detail}" if detail else "")
            ),
        ) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao excluir caso: {exc}",
        ) from exc
    return {
        "message": "Caso excluido. Arquivos removidos; registros da cadeia de custodia preservados.",
        **result,
    }


@router.get("/cases/{case_id}/closure-status", response_model=ClosureStatusResponse)
def get_closure_status(
    case_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    payload = CaseLifecycleService(db).get_closure_status(case_id, current_user)
    return ClosureStatusResponse(**payload)


@router.post("/cases/{case_id}/close", response_model=CloseCaseResultResponse)
def close_case(
    case_id: uuid.UUID,
    request: CloseCaseRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    closure, status_payload = CaseLifecycleService(db).close_case(
        case_id,
        current_user,
        signature_mode=request.signature_mode,
        note=request.note,
    )
    closure_resp = ClosureResponse(
        id=str(closure.id),
        case_id=str(closure.case_id),
        closure_sequence=closure.closure_sequence,
        manifest_sha256=closure.manifest_sha256,
        signature_mode=closure.signature_mode,
        signed_by=str(closure.signed_by),
        signed_at=closure.signed_at.isoformat() if closure.signed_at else "",
        system_signature=closure.system_signature,
    )
    return CloseCaseResultResponse(
        closure=closure_resp,
        case_status=status_payload["case_status"],
        fully_closed=status_payload["fully_closed"],
        closure_status=ClosureStatusResponse(
            **{k: v for k, v in status_payload.items() if k != "signed_now"}
        ),
    )


@router.post("/cases/{case_id}/reopen", response_model=CaseResponse)
def reopen_case(
    case_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    case = CaseLifecycleService(db).reopen_case(case_id, current_user)
    return CaseResponse(
        id=str(case.id),
        protocol_number=case.protocol_number,
        inquiry_number=case.inquiry_number,
        process_number=case.process_number,
        title=case.title,
        description=case.description,
        status=case.status,
        storage_mode=getattr(case, "storage_mode", "va") or "va",
        created_by=str(case.created_by),
        assigned_to=str(case.assigned_to) if case.assigned_to else None,
        created_at=case.created_at.isoformat() if case.created_at else "",
        updated_at=case.updated_at.isoformat() if case.updated_at else "",
    )


@router.post("/cases/{case_id}/close/sign", status_code=status.HTTP_201_CREATED)
def add_closure_signature(
    case_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sig = CaseLifecycleService(db).add_closure_signature(case_id, current_user)
    return {
        "id": str(sig.id),
        "closure_id": str(sig.closure_id),
        "user_id": str(sig.user_id),
        "signed_at": sig.signed_at.isoformat() if sig.signed_at else "",
    }


@router.get("/cases/{case_id}/closures", response_model=List[ClosureResponse])
def list_closures(
    case_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    closures = CaseLifecycleService(db).list_closures(case_id, current_user)
    return [
        ClosureResponse(
            id=str(c.id),
            case_id=str(c.case_id),
            closure_sequence=c.closure_sequence,
            manifest_sha256=c.manifest_sha256,
            signature_mode=c.signature_mode,
            signed_by=str(c.signed_by),
            signed_at=c.signed_at.isoformat() if c.signed_at else "",
            system_signature=c.system_signature,
        )
        for c in closures
    ]
