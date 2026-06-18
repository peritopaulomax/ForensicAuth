"""Peritus case import/export endpoints."""

import tempfile
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from models.case import Case
from models.user import User
from services.peritus_bridge_service import PeritusBridgeService

router = APIRouter()


class PeritusImportResultResponse(BaseModel):
    case_id: str
    protocol_number: str
    storage_mode: str
    evidence_count: int
    derived_count: int
    calculation_count: int
    files_checked: int
    original_zip_sha256: str


async def _save_upload_to_temp(file: UploadFile) -> Path:
    suffix = ".peritus.zip"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            tmp.write(chunk)
        return Path(tmp.name)


@router.post("/cases/peritus/import/validate")
async def validate_case_peritus(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Dry-run: valida pacote Peritus (peritusCase.xml + hashes) sem gravar."""
    tmp_path = await _save_upload_to_temp(file)
    try:
        return PeritusBridgeService(db).validate_package(tmp_path, db=db)
    finally:
        tmp_path.unlink(missing_ok=True)


@router.post("/cases/peritus/import")
async def import_case_peritus(
    file: UploadFile = File(...),
    confirm: bool = Query(False, description="Deve ser true para gravar"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PeritusImportResultResponse | dict[str, Any]:
    """Importa pacote ZIP Peritus nativo (confirm=true)."""
    tmp_path = await _save_upload_to_temp(file)
    try:
        svc = PeritusBridgeService(db)
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
            return PeritusImportResultResponse(**result)
        except HTTPException:
            db.rollback()
            raise
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": "Conflito ao gravar caso Peritus (protocolo ou integridade).",
                    "detail": str(getattr(exc, "orig", exc)),
                },
            ) from exc
        except Exception as exc:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"message": f"Falha na importacao Peritus: {exc}"},
            ) from exc
    finally:
        tmp_path.unlink(missing_ok=True)


@router.post("/cases/{case_id}/peritus/custody/register-files")
def ensure_peritus_files_custody(
    case_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Registra cada arquivo Peritus na cadeia (idempotente; util para casos importados antes da regra)."""
    return PeritusBridgeService(db).ensure_peritus_files_custody(case_id, current_user)


@router.get("/cases/{case_id}/peritus/meta")
def get_peritus_case_meta(
    case_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Metadados do pacote Peritus importado (ancoras de custodia)."""
    return PeritusBridgeService(db).get_case_meta(case_id, current_user)


class PeritusResolveAnalysisRequest(BaseModel):
    path: str


@router.post("/cases/{case_id}/peritus/files/resolve-analysis")
def resolve_peritus_file_for_analysis(
    case_id: uuid.UUID,
    body: PeritusResolveAnalysisRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Resolve arquivo Peritus para evidence_id (materializacao lazy para analise VA)."""
    return PeritusBridgeService(db).resolve_file_for_analysis(case_id, current_user, body.path)


@router.post("/cases/{case_id}/peritus/export")
def export_case_peritus(
    case_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Exporta caso Peritus como ZIP nativo (bit-identico se nao modificado)."""
    tmp = Path(tempfile.gettempdir()) / f"peritus-export-{case_id}.zip"
    PeritusBridgeService(db).export_case(case_id, current_user, tmp)
    case = db.query(Case).filter(Case.id == case_id).first()
    safe = "".join(
        c if c.isalnum() or c in "-_" else "_"
        for c in (case.protocol_number if case else str(case_id))
    )
    return FileResponse(
        path=tmp,
        media_type="application/zip",
        filename=f"peritus-{safe}.zip",
    )


@router.get("/cases/{case_id}/peritus/files")
def list_peritus_files(
    case_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista arquivos do gerenciador Peritus (workspace extraido)."""
    return PeritusBridgeService(db).list_files(case_id, current_user)


@router.get("/cases/{case_id}/peritus/files/thumbnail")
def get_peritus_file_thumbnail(
    case_id: uuid.UUID,
    path: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Thumbnail JPEG para imagem/video no workspace Peritus."""
    from services.peritus_file_meta import infer_file_type
    from services.thumbnail_service import ThumbnailError, generate_thumbnail

    target = PeritusBridgeService(db).resolve_file_path(case_id, current_user, path)
    file_type = infer_file_type(target.name)
    if file_type not in ("imagem", "video"):
        raise HTTPException(status_code=404, detail="Thumbnail indisponivel para este tipo")
    try:
        buf = generate_thumbnail(target, file_type)
    except ThumbnailError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return StreamingResponse(buf, media_type="image/jpeg")


@router.get("/cases/{case_id}/peritus/files/download")
def download_peritus_file(
    case_id: uuid.UUID,
    path: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Download de arquivo do workspace Peritus."""
    target = PeritusBridgeService(db).resolve_file_path(case_id, current_user, path)
    return FileResponse(
        path=target,
        filename=Path(path).name,
        media_type="application/octet-stream",
    )
