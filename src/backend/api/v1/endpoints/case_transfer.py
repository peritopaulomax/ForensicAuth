"""Case export/import (VCP) endpoints."""

import tempfile
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from models.case import Case
from models.user import User
from services.case_transfer_service import CaseTransferService

router = APIRouter()


class ImportResultResponse(BaseModel):
    case_id: str
    protocol_number: str
    chain_valid: bool
    records_imported: int
    evidences_imported: int


async def _save_upload_to_temp(file: UploadFile) -> Path:
    suffix = ".vcp.zip"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            tmp.write(chunk)
        return Path(tmp.name)


@router.post("/cases/{case_id}/export")
def export_case_vcp(
    case_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Exporta caso completo como pacote VCP (.vcp.zip)."""
    tmp = Path(tempfile.gettempdir()) / f"vcp-export-{case_id}.vcp.zip"
    CaseTransferService(db).export_case(case_id, current_user, tmp)
    case = db.query(Case).filter(Case.id == case_id).first()
    safe = "".join(
        c if c.isalnum() or c in "-_" else "_" for c in (case.protocol_number if case else str(case_id))
    )
    return FileResponse(
        path=tmp,
        media_type="application/zip",
        filename=f"caso-{safe}.vcp.zip",
    )


@router.post("/cases/import/validate")
async def validate_case_vcp(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Dry-run: valida pacote VCP sem gravar no banco."""
    tmp_path = await _save_upload_to_temp(file)
    try:
        return CaseTransferService(db).validate_package(tmp_path, db=db)
    finally:
        tmp_path.unlink(missing_ok=True)


@router.post("/cases/import")
async def import_case_vcp(
    file: UploadFile = File(...),
    confirm: bool = Query(False, description="Deve ser true para gravar"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ImportResultResponse | dict[str, Any]:
    """Importa pacote VCP apos validacao (confirm=true)."""
    tmp_path = await _save_upload_to_temp(file)
    try:
        svc = CaseTransferService(db)
        if not confirm:
            report = svc.validate_package(tmp_path, db=db)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": "Envie confirm=true para importar. Relatorio de validacao anexo.",
                    "validation": report,
                },
            )
        try:
            result = svc.import_case(tmp_path, current_user)
            return ImportResultResponse(**result)
        except HTTPException:
            db.rollback()
            raise
        except IntegrityError as exc:
            db.rollback()
            raw = str(getattr(exc, "orig", exc))
            upper = raw.upper()
            if "UNIQUE" in upper and "ANALYSIS_JOBS" in upper:
                msg = (
                    "Job de analise ja existe na base (caso excluido nao foi limpo "
                    "por completo). Reinicie o backend e tente importar novamente."
                )
            elif "FOREIGN KEY" in upper or "foreign key" in raw.lower():
                msg = (
                    "Conflito ao gravar o pacote (integridade referencial). "
                    "Referencia quebrada (ex.: job ou usuario ausente). "
                    "Reinicie o backend e tente novamente."
                )
            else:
                msg = (
                    "Conflito ao gravar o pacote (integridade referencial). "
                    "Reinicie o backend e tente novamente."
                )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"message": msg, "detail": raw},
            ) from exc
        except Exception as exc:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "message": f"Falha na importacao do pacote VCP: {exc}",
                },
            ) from exc
    finally:
        tmp_path.unlink(missing_ok=True)
