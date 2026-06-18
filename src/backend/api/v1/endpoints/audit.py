"""Audit / chain-of-custody endpoints."""

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from models.custody_record import CustodyRecord
from models.user import User
from services.case_access import (
    CaseAccessError,
    accessible_case_ids_subquery,
    get_accessible_case_for_audit,
)
from services.custody_service import CustodyService
from services.custody_signing_service import CustodySigningService
from services.custody_narrative_report import CustodyNarrativeReportService
from services.forensic_integrity_service import ForensicIntegrityService

router = APIRouter()


class CustodyRecordResponse(BaseModel):
    id: str
    record_type: str
    case_id: str
    evidence_id: str | None
    job_id: str | None
    user_id: str
    sha256_input: str | None
    sha256_output: str | None
    sha256_params: str | None
    details: Dict[str, Any]
    previous_record_hash: str | None
    record_hash: str
    timestamp: str


class VerifyRecordResponse(BaseModel):
    valid: bool
    record: CustodyRecordResponse
    computed_hash: str
    signature_valid: bool | None = None


class VerifyChainResponse(BaseModel):
    valid: bool
    records_checked: int
    first_invalid: str | None = None
    reason: str | None = None


def _serialize_record(record: CustodyRecord) -> CustodyRecordResponse:
    return CustodyRecordResponse(
        id=str(record.id),
        record_type=record.record_type,
        case_id=str(record.case_id),
        evidence_id=str(record.evidence_id) if record.evidence_id else None,
        job_id=str(record.job_id) if record.job_id else None,
        user_id=str(record.user_id),
        sha256_input=record.sha256_input,
        sha256_output=record.sha256_output,
        sha256_params=record.sha256_params,
        details=record.details or {},
        previous_record_hash=record.previous_record_hash,
        record_hash=record.record_hash,
        timestamp=record.timestamp.isoformat() if record.timestamp else "",
    )


@router.get("/audit", response_model=List[CustodyRecordResponse])
def list_audit_records(
    case_id: Optional[uuid.UUID] = Query(None),
    evidence_id: Optional[uuid.UUID] = Query(None),
    job_id: Optional[uuid.UUID] = Query(None),
    user_id: Optional[uuid.UUID] = Query(None),
    from_date: Optional[datetime] = Query(None, alias="from"),
    to_date: Optional[datetime] = Query(None, alias="to"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List custody records with optional filters. Ordered by timestamp descending."""
    query = db.query(CustodyRecord)

    if case_id:
        get_accessible_case_for_audit(db, case_id, current_user)
        query = query.filter(CustodyRecord.case_id == case_id)
    else:
        allowed_ids = accessible_case_ids_subquery(db, current_user)
        query = query.filter(CustodyRecord.case_id.in_(allowed_ids))

    if evidence_id:
        query = query.filter(CustodyRecord.evidence_id == evidence_id)
    if job_id:
        query = query.filter(CustodyRecord.job_id == job_id)
    if user_id:
        query = query.filter(CustodyRecord.user_id == user_id)
    if from_date:
        query = query.filter(CustodyRecord.timestamp >= from_date)
    if to_date:
        query = query.filter(CustodyRecord.timestamp <= to_date)

    records = query.order_by(CustodyRecord.timestamp.desc()).all()
    return [_serialize_record(r) for r in records]


@router.get("/audit/verify/{record_id}", response_model=VerifyRecordResponse)
def verify_record(
    record_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Verify the hash of a single custody record."""
    record = db.query(CustodyRecord).filter(CustodyRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Registro nao encontrado")

    try:
        get_accessible_case_for_audit(db, record.case_id, current_user)
    except CaseAccessError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado")

    service = CustodyService(db)
    try:
        result = service.verify_record(record_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    rec = result["record"]
    return VerifyRecordResponse(
        valid=result["valid"],
        record=_serialize_record(rec),
        computed_hash=result["computed_hash"],
        signature_valid=result.get("signature_valid"),
    )


@router.get("/audit/verify-case/{case_id}", response_model=VerifyChainResponse)
def verify_case_chain(
    case_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Verify the full custody chain integrity for a case."""
    get_accessible_case_for_audit(db, case_id, current_user)
    service = CustodyService(db)
    result = service.verify_chain(case_id)
    return VerifyChainResponse(**result)


@router.get("/audit/signing-keys")
def get_signing_keys(
    current_user: User = Depends(get_current_user),
):
    """Public Ed25519 key for offline verification."""
    signing = CustodySigningService()
    return {
        "signing_key_id": signing.key_id,
        "public_key_pem": signing.public_key_pem(),
    }


@router.get("/audit/verify-case-forensic/{case_id}")
def verify_case_forensic(
    case_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Full forensic integrity report (chain, files, provenance, closures)."""
    get_accessible_case_for_audit(db, case_id, current_user)
    return ForensicIntegrityService(db).verify_case_forensic_integrity(case_id)


@router.get("/audit/verify-case-forensic/{case_id}/report")
def verify_case_forensic_report(
    case_id: uuid.UUID,
    format: str = Query("json", pattern="^(json|html)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    get_accessible_case_for_audit(db, case_id, current_user)
    report = ForensicIntegrityService(db).verify_case_forensic_integrity(case_id)
    records = (
        db.query(CustodyRecord)
        .filter(CustodyRecord.case_id == case_id)
        .order_by(CustodyRecord.chain_sequence.asc())
        .all()
    )
    report["timeline"] = [
        {
            "id": str(r.id),
            "record_type": r.record_type,
            "timestamp": r.timestamp.isoformat() if r.timestamp else "",
            "chain_sequence": r.chain_sequence,
        }
        for r in records
    ]
    if format == "html":
        body = (
            "<html><head><meta charset='utf-8'><title>Relatorio Forense</title></head><body>"
            f"<h1>Verificacao forense — caso {case_id}</h1>"
            f"<pre>{json.dumps(report, indent=2, ensure_ascii=False)}</pre>"
            "</body></html>"
        )
        return HTMLResponse(
            content=body,
            headers={
                "Content-Disposition": f'attachment; filename="forensic-report-{case_id}.html"'
            },
        )
    return JSONResponse(
        content=report,
        headers={
            "Content-Disposition": f'attachment; filename="forensic-report-{case_id}.json"'
        },
    )


@router.get("/audit/case/{case_id}/narrative-report")
def custody_narrative_report(
    case_id: uuid.UUID,
    format: str = Query("html", pattern="^(html|md)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Relatorio narrativo da cadeia de custodia (HTML ou Markdown)."""
    get_accessible_case_for_audit(db, case_id, current_user)
    try:
        report = CustodyNarrativeReportService(db).build(case_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    svc = CustodyNarrativeReportService(db)
    protocol = report["case"].get("protocol_number", str(case_id))
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in protocol)

    if format == "md":
        body = svc.render_markdown(report)
        return Response(
            content=body,
            media_type="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="cadeia-custodia-{safe_name}.md"'
                )
            },
        )

    body = svc.render_html(report)
    return HTMLResponse(
        content=body,
        headers={
            "Content-Disposition": (
                f'attachment; filename="cadeia-custodia-{safe_name}.html"'
            )
        },
    )
