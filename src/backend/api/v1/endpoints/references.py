"""Reference materials — technique papers, bibliographies."""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse

from app.dependencies import get_current_user
from core.references.imdl_papers import (
    get_paper_metadata,
    list_paper_technique_ids,
    resolve_paper_file_path,
    resolve_paper_path,
    suggested_download_filename,
)
from models.user import User

router = APIRouter()


@router.get("/references/papers/imdl")
def list_imdl_papers(
    current_user: User = Depends(get_current_user),
):
    """Lista metadados dos PDFs IML/DL disponíveis localmente."""
    del current_user
    items = []
    for technique_id in list_paper_technique_ids():
        meta = get_paper_metadata(technique_id)
        if meta:
            items.append(meta)
    return {"papers": items}


@router.get("/references/papers/imdl/{technique_id}")
def get_imdl_paper(
    technique_id: str,
    current_user: User = Depends(get_current_user),
):
    """Metadados de um artigo IML/DL (disponibilidade e tamanho do PDF local)."""
    del current_user
    try:
        meta = get_paper_metadata(technique_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if meta is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artigo nao catalogado.")
    return meta


@router.get("/references/papers/imdl/{technique_id}/file")
def download_imdl_paper(
    technique_id: str,
    current_user: User = Depends(get_current_user),
):
    """Download do PDF local do artigo."""
    del current_user
    try:
        path = resolve_paper_path(technique_id)
        filename = suggested_download_filename(technique_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="PDF do artigo nao encontrado no servidor.",
        )
    return FileResponse(
        path=str(path),
        media_type="application/pdf",
        filename=filename,
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.get("/references/papers/imdl/{technique_id}/file/{paper_index}")
def download_imdl_paper_by_index(
    technique_id: str,
    paper_index: int,
    current_user: User = Depends(get_current_user),
):
    """Download de um PDF local específico quando a técnica possui múltiplos artigos."""
    del current_user
    if paper_index < 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Indice de artigo invalido.")
    try:
        path = resolve_paper_file_path(technique_id, paper_index)
        filename = suggested_download_filename(technique_id, paper_index)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="PDF do artigo nao encontrado no servidor.",
        )
    return FileResponse(
        path=str(path),
        media_type="application/pdf",
        filename=filename,
        headers={"Cache-Control": "private, max-age=3600"},
    )
