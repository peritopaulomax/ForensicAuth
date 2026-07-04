"""Case visibility and access control by user role and shares."""

import uuid
from typing import Literal, Optional

from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Query, Session

from models.analysis_job import AnalysisJob
from models.case import Case
from models.case_share import CaseShare
from models.evidence import Evidence
from models.user import User

CaseAccessLevel = Literal["owner", "assigned", "shared_editor", "shared_viewer", "admin"]

_ALLOWED_ROLES = frozenset({"admin", "perito"})


class CaseAccessError(HTTPException):
    def __init__(self, detail: str = "Caso nao encontrado"):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def _active_share_subquery(db: Session, user_id: uuid.UUID):
    return (
        db.query(CaseShare.case_id)
        .filter(
            CaseShare.shared_with_user_id == user_id,
            CaseShare.revoked_at.is_(None),
        )
        .subquery()
    )


def _is_owner(case: Case, user: User) -> bool:
    return case.created_by == user.id


def _is_assigned(case: Case, user: User) -> bool:
    return case.assigned_to == user.id


def _perito_case_filter(user_id: uuid.UUID):
    """Casos criados pelo perito ou atribuidos a ele (delegacao)."""
    return or_(Case.created_by == user_id, Case.assigned_to == user_id)


def get_active_share(db: Session, case_id: uuid.UUID, user_id: uuid.UUID) -> CaseShare | None:
    return (
        db.query(CaseShare)
        .filter(
            CaseShare.case_id == case_id,
            CaseShare.shared_with_user_id == user_id,
            CaseShare.revoked_at.is_(None),
        )
        .first()
    )


def get_case_access_level(db: Session, case: Case, user: User) -> CaseAccessLevel | None:
    if user.role == "admin":
        return "admin"
    if _is_owner(case, user):
        return "owner"
    if _is_assigned(case, user):
        return "assigned"
    share = get_active_share(db, case.id, user.id)
    if share:
        if share.role == "editor":
            return "shared_editor"
        return "shared_viewer"
    return None


def cases_query_for_user(
    db: Session,
    user: User,
    *,
    include_deleted: bool = False,
    scope: Optional[str] = None,
) -> Query:
    """Return a query scoped to cases the user may access.

    scope: mine | shared | all (default all accessible)
    """
    query = db.query(Case)
    if not include_deleted:
        query = query.filter(Case.deleted_at.is_(None))

    if user.role == "admin":
        if scope == "shared":
            return query.filter(False)
        return query

    shared_ids = _active_share_subquery(db, user.id)
    owned_filter = _perito_case_filter(user.id)

    if scope == "mine":
        return query.filter(owned_filter)
    if scope == "shared":
        return query.filter(
            Case.id.in_(shared_ids),
            Case.created_by != user.id,
            or_(Case.assigned_to.is_(None), Case.assigned_to != user.id),
        )
    return query.filter(or_(owned_filter, Case.id.in_(shared_ids)))


def get_accessible_case(db: Session, case_id: uuid.UUID, user: User) -> Case:
    """Fetch a case if the user is allowed to access it (nao excluido)."""
    case = db.query(Case).filter(Case.id == case_id, Case.deleted_at.is_(None)).first()
    if not case:
        raise CaseAccessError()
    if get_case_access_level(db, case, user) is None:
        raise CaseAccessError()
    return case


def assert_can_edit_case(db: Session, case: Case, user: User) -> None:
    """Mutations: owner, admin, perito atribuido, or shared editor."""
    level = get_case_access_level(db, case, user)
    if level in ("admin", "owner"):
        return
    if level == "assigned":
        return
    if level == "shared_editor":
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Sem permissao para editar este caso",
    )


def assert_can_share_case(db: Session, case: Case, user: User) -> None:
    if user.role == "admin":
        return
    if _is_owner(case, user):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Apenas o criador do caso ou admin pode compartilhar",
    )


def get_required_closure_signer_ids(db: Session, case: Case) -> list[uuid.UUID]:
    """Participantes que devem assinar o fechamento (criador, atribuido, editores compartilhados)."""
    signer_ids: set[uuid.UUID] = {case.created_by}
    if case.assigned_to:
        signer_ids.add(case.assigned_to)
    shares = (
        db.query(CaseShare)
        .filter(
            CaseShare.case_id == case.id,
            CaseShare.revoked_at.is_(None),
            CaseShare.role == "editor",
        )
        .all()
    )
    for share in shares:
        signer_ids.add(share.shared_with_user_id)
    return sorted(signer_ids, key=lambda x: str(x))


def user_may_sign_closure(db: Session, case: Case, user: User) -> bool:
    if user.role == "admin":
        return True
    return user.id in get_required_closure_signer_ids(db, case)


def assert_can_close_case(db: Session, case: Case, user: User) -> None:
    """Iniciar ou assinar fechamento bilateral."""
    if user_may_sign_closure(db, case, user):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Sem permissao para fechar ou assinar o fechamento deste caso",
    )


def assert_can_reopen_case(db: Session, case: Case, user: User) -> None:
    assert_can_close_case(db, case, user)


def assert_case_not_closed(case: Case) -> None:
    if case.status in ("fechado", "fechamento_pendente"):
        label = (
            "Fechamento pendente de assinaturas"
            if case.status == "fechamento_pendente"
            else "Caso fechado"
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{label} — operacao nao permitida",
        )


def assert_can_delete_case(case: Case, user: User) -> None:
    """Perito: proprio caso; admin: qualquer caso."""
    if case.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Caso ja foi excluido",
        )
    if user.role == "admin":
        return
    if case.created_by == user.id:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Sem permissao para excluir este caso",
    )


def get_accessible_evidence(db: Session, evidence_id: uuid.UUID, user: User):
    """Fetch evidence if its parent case is accessible to the user."""
    evidence = (
        db.query(Evidence)
        .filter(Evidence.id == evidence_id, Evidence.deleted_at.is_(None))
        .first()
    )
    if not evidence:
        raise CaseAccessError("Evidencia nao encontrada")
    get_accessible_case(db, evidence.case_id, user)
    return evidence


def get_accessible_case_for_audit(db: Session, case_id: uuid.UUID, user: User) -> Case:
    """Fetch a case for audit (inclui casos excluidos — cadeia preservada)."""
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise CaseAccessError()
    if user.role == "admin":
        return case
    if case.deleted_at is not None:
        if get_case_access_level(db, case, user) is not None:
            return case
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso negado",
        )
    get_accessible_case(db, case_id, user)
    return case


def accessible_case_ids_subquery(db: Session, user: User):
    """Return case IDs the user may audit."""
    if user.role == "admin":
        return db.query(Case.id)
    return cases_query_for_user(db, user).with_entities(Case.id)


def get_accessible_job(db: Session, job_id: uuid.UUID, user: User) -> "AnalysisJob":
    """Fetch analysis job if its parent evidence case is accessible."""
    job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
    if not job:
        raise CaseAccessError("Job nao encontrado")
    get_accessible_evidence(db, job.evidence_id, user)
    return job


def assert_can_create_case(user: User) -> None:
    if user.role not in _ALLOWED_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sem permissao para criar casos",
        )
