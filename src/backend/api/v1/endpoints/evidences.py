"""Evidence endpoints — upload and management."""

import uuid
from pathlib import Path
from typing import Any, List

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from models.user import User
from services.evidence_service import EvidenceService, EvidenceUploadError
from services.case_access import (
    assert_can_edit_case,
    assert_case_not_closed,
    get_accessible_case,
    get_accessible_evidence,
    get_accessible_job,
)
from models.case import Case


def _require_case_mutable(db: Session, case_id: uuid.UUID, user: User) -> Case:
    case = get_accessible_case(db, case_id, user)
    assert_can_edit_case(db, case, user)
    assert_case_not_closed(case)
    return case
from services.derivative_service import DerivativeAlreadySaved, DerivativeSaveError, DerivativeService
from services.evidence_classification import (
    group_global_references,
    group_references,
    is_case_evidence,
    is_derived,
)
from services.audio_evidence_metadata import ensure_audio_technical_metadata

router = APIRouter()


class EvidenceResponse(BaseModel):
    id: str
    case_id: str
    filename: str
    original_filename: str
    file_size: int
    file_type: str
    mime_type: str | None
    sha256: str
    extra_metadata: dict
    uploaded_by: str
    created_at: str

    class Config:
        from_attributes = True


class SaveDerivativeRequest(BaseModel):
    job_id: uuid.UUID
    artifact_filename: str = Field(default="heatmap.png", min_length=1)
    label: str | None = Field(default=None, max_length=255)
    effective_parameters: dict[str, Any] | None = None


class SaveDerivativeResponse(BaseModel):
    evidence: EvidenceResponse
    message: str


class LineageNodeResponse(BaseModel):
    evidence_id: str
    original_filename: str
    file_type: str
    sha256: str
    is_derived: bool
    is_synthetic: bool | None = None
    synthetic_kind: str | None = None
    technique: str | None = None
    parameters: dict | None = None
    procedure_summary: str | None = None
    artifact_role: str | None = None
    derivation_outputs: dict | None = None
    derivation_step: str | None = None
    source_job_id: str | None = None
    derivation_group_id: str | None = None
    legacy_provenance: bool | None = None
    layer: int | None = None
    images_used: int | None = None


class LineageEdgeResponse(BaseModel):
    from_evidence_id: str
    to_evidence_id: str
    technique: str | None = None
    parameters: dict = Field(default_factory=dict)
    procedure_summary: str | None = None
    source_job_id: str | None = None
    derivation_step: str | None = None


class LineageOperationResponse(BaseModel):
    id: str
    to_evidence_id: str
    derivation_step: str | None = None
    label: str
    inputs: List[dict] = Field(default_factory=list)
    outputs: dict | None = None
    input_count: int | None = None
    images_used: int | None = None


class LineagePhaseResponse(BaseModel):
    layer: int
    label: str
    node_ids: List[str] = Field(default_factory=list)
    node_count: int | None = None


class DerivationGroupResponse(BaseModel):
    derivation_group_id: str
    source_job_id: str | None = None
    member_count: int
    siblings: List[dict] = Field(default_factory=list)


class LineageGraphResponse(BaseModel):
    target_id: str
    case_id: str
    layout: str = "dag"
    layout_label: str | None = None
    parent_count: int | None = None
    nodes: List[LineageNodeResponse]
    edges: List[LineageEdgeResponse]
    operations: List[LineageOperationResponse] = Field(default_factory=list)
    phases: List[LineagePhaseResponse] = Field(default_factory=list)
    derivation_groups: List[DerivationGroupResponse] = Field(default_factory=list)
    legacy_notes: List[str] = Field(default_factory=list)


class ReferenceGroupResponse(BaseModel):
    technique: str
    group_label: str
    display_label: str
    files: List[EvidenceResponse]


class GlobalReferenceGroupResponse(BaseModel):
    reference_type: str
    group_label: str
    display_label: str
    files: List[EvidenceResponse]


class CaseReferencesResponse(BaseModel):
    groups: List[ReferenceGroupResponse]
    global_groups: List[GlobalReferenceGroupResponse]


class AudioTechnicalMetadataResponse(BaseModel):
    evidence_id: str
    sample_rate_hz: int | None = None
    duration_sec: float | None = None
    bit_depth: int | None = None
    codec: str | None = None
    channels: int | None = None


class CaseAudioMetadataResponse(BaseModel):
    items: List[AudioTechnicalMetadataResponse]


def _to_evidence_response(evidence) -> EvidenceResponse:
    return EvidenceResponse(
        id=str(evidence.id),
        case_id=str(evidence.case_id),
        filename=evidence.filename,
        original_filename=evidence.original_filename,
        file_size=evidence.file_size,
        file_type=evidence.file_type,
        mime_type=evidence.mime_type,
        sha256=evidence.sha256,
        extra_metadata=evidence.extra_metadata or {},
        uploaded_by=str(evidence.uploaded_by),
        created_at=evidence.created_at.isoformat() if evidence.created_at else "",
    )


@router.post("/evidences/upload", status_code=status.HTTP_201_CREATED, response_model=EvidenceResponse)
def upload_evidence(
    case_id: uuid.UUID = Form(..., description="UUID do caso"),
    file: UploadFile = File(..., description="Arquivo de evidencia"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload a new evidence file to a case."""
    _require_case_mutable(db, case_id, current_user)
    service = EvidenceService(db)
    try:
        evidence = service.upload_evidence(
            case_id=case_id,
            filename=file.filename or "unknown",
            mime_type=file.content_type,
            file_obj=file.file,
            uploaded_by=current_user.id,
        )
    except EvidenceUploadError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(e),
        )

    return EvidenceResponse(
        id=str(evidence.id),
        case_id=str(evidence.case_id),
        filename=evidence.filename,
        original_filename=evidence.original_filename,
        file_size=evidence.file_size,
        file_type=evidence.file_type,
        mime_type=evidence.mime_type,
        sha256=evidence.sha256,
        extra_metadata=evidence.extra_metadata or {},
        uploaded_by=str(evidence.uploaded_by),
        created_at=evidence.created_at.isoformat() if evidence.created_at else "",
    )


@router.post("/evidences/prnu-reference-upload", status_code=status.HTTP_201_CREATED, response_model=EvidenceResponse)
def upload_prnu_reference(
    case_id: uuid.UUID = Form(..., description="UUID do caso"),
    group_label: str = Form(..., min_length=1, max_length=120, description="Rotulo do grupo (ex.: D70)"),
    file: UploadFile = File(..., description="Imagem de referencia PRNU"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload reference images for PRNU fingerprint generation (custody chain)."""
    _require_case_mutable(db, case_id, current_user)
    rotulo = group_label.strip()
    if not rotulo:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Informe o rotulo do grupo de referencia",
        )
    service = EvidenceService(db)
    try:
        evidence = service.upload_evidence(
            case_id=case_id,
            filename=file.filename or "unknown",
            mime_type=file.content_type,
            file_obj=file.file,
            uploaded_by=current_user.id,
            extra_metadata={
                "is_reference": True,
                "reference_technique": "prnu",
                "reference_group_label": rotulo,
                "prnu_reference": True,
                "for_technique": "prnu",
                "role": "fingerprint_source",
            },
        )
    except EvidenceUploadError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(e),
        )

    return _to_evidence_response(evidence)


@router.post(
    "/evidences/pdf-structure-reference-upload",
    status_code=status.HTTP_201_CREATED,
    response_model=EvidenceResponse,
)
def upload_pdf_structure_reference(
    case_id: uuid.UUID = Form(..., description="UUID do caso"),
    group_label: str = Form(..., min_length=1, max_length=120, description="Rotulo do grupo"),
    file: UploadFile = File(..., description="PDF de referencia estrutural"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload PDFs de referencia para matriz de similaridade estrutural."""
    _require_case_mutable(db, case_id, current_user)
    rotulo = group_label.strip()
    if not rotulo:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Informe o rotulo do grupo de referencia",
        )
    if file.filename and not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Apenas arquivos PDF sao aceitos como referencia estrutural",
        )
    service = EvidenceService(db)
    try:
        evidence = service.upload_evidence(
            case_id=case_id,
            filename=file.filename or "reference.pdf",
            mime_type=file.content_type or "application/pdf",
            file_obj=file.file,
            uploaded_by=current_user.id,
            extra_metadata={
                "is_reference": True,
                "reference_technique": "pdf_structure_similarity",
                "reference_group_label": rotulo,
                "for_technique": "pdf_structure_similarity",
                "role": "structure_reference",
            },
        )
    except EvidenceUploadError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(e),
        )
    return _to_evidence_response(evidence)


@router.post(
    "/evidences/isom-structure-reference-upload",
    status_code=status.HTTP_201_CREATED,
    response_model=EvidenceResponse,
)
def upload_isom_structure_reference(
    case_id: uuid.UUID = Form(..., description="UUID do caso"),
    group_label: str = Form(..., min_length=1, max_length=120, description="Rotulo do grupo"),
    file: UploadFile = File(..., description="Video de referencia estrutural ISO BMFF"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload de videos de referencia para similaridade estrutural ISO BMFF."""
    _require_case_mutable(db, case_id, current_user)
    rotulo = group_label.strip()
    if not rotulo:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Informe o rotulo do grupo de referencia",
        )
    allowed_ext = {".mp4", ".mov", ".m4v", ".3gp", ".m4a", ".f4v", ".m4r", ".m4b", ".m4p", ".heic"}
    ext = Path(file.filename or "").suffix.lower()
    if ext and ext not in allowed_ext:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Referencia ISO BMFF aceita MP4/MOV/M4V/3GP e derivados ISOBMFF",
        )
    service = EvidenceService(db)
    try:
        evidence = service.upload_evidence(
            case_id=case_id,
            filename=file.filename or "reference.mp4",
            mime_type=file.content_type or "video/mp4",
            file_obj=file.file,
            uploaded_by=current_user.id,
            extra_metadata={
                "is_reference": True,
                "reference_technique": "isomedia_compare",
                "reference_group_label": rotulo,
                "for_technique": "isomedia_compare",
                "role": "structure_reference",
            },
        )
    except EvidenceUploadError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(e),
        )
    return _to_evidence_response(evidence)


@router.post(
    "/evidences/jpeg-structure-reference-upload",
    status_code=status.HTTP_201_CREATED,
    response_model=EvidenceResponse,
)
def upload_jpeg_structure_reference(
    case_id: uuid.UUID = Form(..., description="UUID do caso"),
    group_label: str = Form(..., min_length=1, max_length=120, description="Rotulo do grupo"),
    file: UploadFile = File(..., description="Imagem JPEG de referencia estrutural"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload de imagens JPEG de referencia para matriz de estrutura."""
    _require_case_mutable(db, case_id, current_user)
    rotulo = group_label.strip()
    if not rotulo:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Informe o rotulo do grupo de referencia",
        )
    allowed_ext = {".jpg", ".jpeg", ".jfif"}
    ext = Path(file.filename or "").suffix.lower()
    if ext and ext not in allowed_ext:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Referencia JPEG aceita .jpg, .jpeg ou .jfif",
        )
    service = EvidenceService(db)
    try:
        evidence = service.upload_evidence(
            case_id=case_id,
            filename=file.filename or "reference.jpg",
            mime_type=file.content_type or "image/jpeg",
            file_obj=file.file,
            uploaded_by=current_user.id,
            extra_metadata={
                "is_reference": True,
                "reference_technique": "jpeg_structure_compare",
                "reference_group_label": rotulo,
                "for_technique": "jpeg_structure_compare",
                "role": "structure_reference",
            },
        )
    except EvidenceUploadError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(e),
        )
    return _to_evidence_response(evidence)


@router.post("/evidences/reference-upload", status_code=status.HTTP_201_CREATED, response_model=EvidenceResponse)
def upload_reference(
    case_id: uuid.UUID = Form(..., description="UUID do caso"),
    file: UploadFile = File(..., description="Arquivo de referencia (JPEG)"),
    group_label: str = Form(default="Padrao", max_length=120, description="Rotulo do grupo"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload a reference image for DCT quantization analysis.

    The reference image is stored as an evidence record with metadata
    flagging it as a reference for custody chain tracking.
    """
    _require_case_mutable(db, case_id, current_user)
    rotulo = (group_label or "Padrao").strip() or "Padrao"
    service = EvidenceService(db)
    try:
        evidence = service.upload_evidence(
            case_id=case_id,
            filename=file.filename or "unknown",
            mime_type=file.content_type,
            file_obj=file.file,
            uploaded_by=current_user.id,
            extra_metadata={
                "is_reference": True,
                "reference_technique": "dct_quantization",
                "reference_group_label": rotulo,
                "reference": True,
                "for_technique": "dct_quantization",
            },
        )
    except EvidenceUploadError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(e),
        )

    return EvidenceResponse(
        id=str(evidence.id),
        case_id=str(evidence.case_id),
        filename=evidence.filename,
        original_filename=evidence.original_filename,
        file_size=evidence.file_size,
        file_type=evidence.file_type,
        mime_type=evidence.mime_type,
        sha256=evidence.sha256,
        extra_metadata=evidence.extra_metadata or {},
        uploaded_by=str(evidence.uploaded_by),
        created_at=evidence.created_at.isoformat() if evidence.created_at else "",
    )


@router.post("/evidences/global-reference-upload", status_code=status.HTTP_201_CREATED, response_model=EvidenceResponse)
def upload_global_reference(
    case_id: uuid.UUID = Form(..., description="UUID do caso"),
    file: UploadFile = File(..., description="Arquivo de referencia"),
    group_label: str = Form(..., min_length=1, max_length=120, description="Rotulo do grupo de referencias"),
    reference_type: str = Form(..., pattern="^(imagem|video|audio|pdf)$", description="Tipo da referencia"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload a labeled global reference file (image, video, audio or PDF).

    Reference files are stored as evidence records and grouped by label/type.
    They become available as selectable inputs across compatible analysis plugins.
    """
    _require_case_mutable(db, case_id, current_user)
    rotulo = (group_label or "Sem rotulo").strip() or "Sem rotulo"
    ref_type = (reference_type or "").strip().lower()
    type_map = {
        "imagem": "imagem",
        "video": "video",
        "audio": "audio",
        "pdf": "pdf",
    }
    expected = type_map.get(ref_type)

    service = EvidenceService(db)
    try:
        inferred = service._infer_file_type(file.content_type, file.filename or "")
    except EvidenceUploadError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Tipo de arquivo invalido para referencia '{ref_type}'. Somente arquivos {expected} sao aceitos.",
        )
    if inferred != expected:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Tipo de arquivo invalido para referencia '{ref_type}'. Esperado: {expected}, obtido: {inferred}.",
        )

    try:
        evidence = service.upload_evidence(
            case_id=case_id,
            filename=file.filename or "unknown",
            mime_type=file.content_type,
            file_obj=file.file,
            uploaded_by=current_user.id,
            extra_metadata={
                "is_reference": True,
                "reference_scope": "global",
                "reference_type": ref_type,
                "reference_group_label": rotulo,
            },
        )
    except EvidenceUploadError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(e),
        )

    return _to_evidence_response(evidence)


@router.post("/evidences/derivatives", status_code=status.HTTP_201_CREATED, response_model=SaveDerivativeResponse)
def save_derivative(
    request: SaveDerivativeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Save a completed analysis artifact as derived evidence with custody registration."""
    job = get_accessible_job(db, request.job_id, current_user)
    from models.evidence import Evidence as EvidenceModel

    parent = db.query(EvidenceModel).filter(EvidenceModel.id == job.evidence_id).first()
    if parent:
        _require_case_mutable(db, parent.case_id, current_user)
    service = DerivativeService(db)
    try:
        derivative = service.save_from_job(
            job_id=request.job_id,
            artifact_filename=request.artifact_filename,
            user_id=current_user.id,
            label=request.label,
            effective_parameters=request.effective_parameters,
        )
    except DerivativeSaveError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(e),
        )
    except DerivativeAlreadySaved as e:
        payload = SaveDerivativeResponse(
            evidence=_to_evidence_response(e.evidence),
            message="Este artefato ja foi salvo como evidencia derivada",
        )
        return JSONResponse(status_code=status.HTTP_200_OK, content=jsonable_encoder(payload))

    return SaveDerivativeResponse(
        evidence=_to_evidence_response(derivative),
        message="Derivado salvo e registrado na cadeia de custodia",
    )


@router.delete("/evidences/{evidence_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_evidence(
    evidence_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete an evidence file after recording the action in the custody chain."""
    evidence = get_accessible_evidence(db, evidence_id, current_user)
    _require_case_mutable(db, evidence.case_id, current_user)
    service = EvidenceService(db)
    try:
        service.delete_evidence(evidence_id, deleted_by=current_user.id)
    except EvidenceUploadError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.get("/evidences/{evidence_id}/thumbnail")
def get_evidence_thumbnail(
    evidence_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Serve a small JPEG thumbnail for image or video evidences."""
    evidence = get_accessible_evidence(db, evidence_id, current_user)

    if evidence.file_type not in ("imagem", "video"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Thumbnail disponivel apenas para imagens e videos",
        )

    file_path = Path(evidence.file_path)
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Arquivo nao encontrado no disco",
        )

    from services.thumbnail_service import ThumbnailError, generate_thumbnail

    try:
        buf = generate_thumbnail(file_path, evidence.file_type)
    except ThumbnailError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Falha ao gerar thumbnail",
        )

    return StreamingResponse(buf, media_type="image/jpeg")


@router.get("/evidences/{evidence_id}/file")
def get_evidence_file(
    evidence_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Serve the actual evidence file for download/preview."""
    evidence = get_accessible_evidence(db, evidence_id, current_user)

    file_path = Path(evidence.file_path)
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Arquivo nao encontrado no disco",
        )

    return FileResponse(
        str(file_path),
        filename=evidence.original_filename,
        media_type=evidence.mime_type or "application/octet-stream",
    )


@router.get("/evidences/{evidence_id}/lineage", response_model=LineageGraphResponse)
def get_evidence_lineage(
    evidence_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return derivation chain from root evidence to the requested evidence."""
    get_accessible_evidence(db, evidence_id, current_user)
    service = DerivativeService(db)
    try:
        graph = service.get_lineage(evidence_id)
    except DerivativeSaveError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return LineageGraphResponse(**graph)


@router.get("/evidences/{evidence_id}", response_model=EvidenceResponse)
def get_evidence(
    evidence_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve evidence metadata by ID."""
    evidence = get_accessible_evidence(db, evidence_id, current_user)

    return EvidenceResponse(
        id=str(evidence.id),
        case_id=str(evidence.case_id),
        filename=evidence.filename,
        original_filename=evidence.original_filename,
        file_size=evidence.file_size,
        file_type=evidence.file_type,
        mime_type=evidence.mime_type,
        sha256=evidence.sha256,
        extra_metadata=evidence.extra_metadata or {},
        uploaded_by=str(evidence.uploaded_by),
        created_at=evidence.created_at.isoformat() if evidence.created_at else "",
    )


@router.get("/cases/{case_id}/evidences", response_model=List[EvidenceResponse])
def list_case_evidences(
    case_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all evidences for a specific case."""
    get_accessible_case(db, case_id, current_user)
    from models.evidence import Evidence

    evidences = (
        db.query(Evidence)
        .filter(Evidence.case_id == case_id, Evidence.deleted_at.is_(None))
        .order_by(Evidence.created_at.desc())
        .all()
    )
    case_evidences = [e for e in evidences if is_case_evidence(e)]
    return [_to_evidence_response(e) for e in case_evidences]


@router.get("/cases/{case_id}/audio-metadata", response_model=CaseAudioMetadataResponse)
def list_case_audio_metadata(
    case_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Metadados tecnicos (taxa, duracao, bits, codec) dos audios do caso."""
    get_accessible_case(db, case_id, current_user)
    from models.evidence import Evidence

    evidences = (
        db.query(Evidence)
        .filter(
            Evidence.case_id == case_id,
            Evidence.deleted_at.is_(None),
            Evidence.file_type == "audio",
        )
        .order_by(Evidence.created_at.desc())
        .all()
    )
    case_audio = [e for e in evidences if is_case_evidence(e)]

    items: List[AudioTechnicalMetadataResponse] = []
    for evidence in case_audio:
        technical = ensure_audio_technical_metadata(evidence, db)
        items.append(
            AudioTechnicalMetadataResponse(
                evidence_id=str(evidence.id),
                sample_rate_hz=technical.get("sample_rate_hz"),
                duration_sec=technical.get("duration_sec"),
                bit_depth=technical.get("bit_depth"),
                codec=technical.get("codec"),
                channels=technical.get("channels"),
            )
        )
    return CaseAudioMetadataResponse(items=items)


@router.get("/cases/{case_id}/references", response_model=CaseReferencesResponse)
def list_case_references(
    case_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List technique reference files grouped by technique and rotulo."""
    get_accessible_case(db, case_id, current_user)
    from models.evidence import Evidence

    evidences = (
        db.query(Evidence)
        .filter(Evidence.case_id == case_id, Evidence.deleted_at.is_(None))
        .order_by(Evidence.created_at.desc())
        .all()
    )
    plugin_groups = group_references(evidences)
    global_groups = group_global_references(evidences)
    return CaseReferencesResponse(
        groups=[
            ReferenceGroupResponse(
                technique=g["technique"],
                group_label=g["group_label"],
                display_label=g["display_label"],
                files=[_to_evidence_response(e) for e in g["evidences"]],
            )
            for g in plugin_groups
        ],
        global_groups=[
            GlobalReferenceGroupResponse(
                reference_type=g["reference_type"],
                group_label=g["group_label"],
                display_label=g["display_label"],
                files=[_to_evidence_response(e) for e in g["evidences"]],
            )
            for g in global_groups
        ],
    )


@router.get("/cases/{case_id}/derivatives", response_model=List[EvidenceResponse])
def list_case_derivatives(
    case_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List derived evidences for a case (registered in custody chain)."""
    get_accessible_case(db, case_id, current_user)
    from models.evidence import Evidence

    evidences = (
        db.query(Evidence)
        .filter(Evidence.case_id == case_id, Evidence.deleted_at.is_(None))
        .order_by(Evidence.created_at.desc())
        .all()
    )
    derived = [
        e for e in evidences if is_derived(e) and not (e.extra_metadata or {}).get("peritus_import")
    ]
    return [_to_evidence_response(e) for e in derived]
