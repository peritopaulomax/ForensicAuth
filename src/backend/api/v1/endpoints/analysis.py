"""Analysis endpoints — job submission, status, results, techniques."""

import uuid
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.dependencies import get_current_user
from core.plugin_contracts import provenance_contract
from core.result_handlers import (
    AUDIO_PLOT_SNAPSHOT_FILENAMES,
    has_display_handler,
    has_preview_handler,
    has_snapshot_handler,
    load_display_data,
    preview,
    store_snapshot,
)
from models.user import User
from services.case_access import (
    assert_can_edit_case,
    assert_case_not_closed,
    get_accessible_evidence,
)
from services.job_runner import run_job_in_background
from services.job_service import JobService, build_job_result_dir

router = APIRouter()

# Perito: CAT-Net, TruFor, MIML APSC-Net. Demais métodos IMDL: só admin.
IMDL_ADMIN_ONLY_METHODS = {
    "sparse_vit",
    "mesorch",
    "dinov3_iml",
    "co_transformers",
    "nfa_vit",
    "objectformer",
    "forensic_hub",
    "opensdi",
}
# Plugins de localização fora do hub IMDL restritos a admin.
ADMIN_ONLY_TECHNIQUES = {"safire"}


class SubmitJobRequest(BaseModel):
    evidence_id: uuid.UUID
    technique: str = Field(..., min_length=1)
    parameters: Dict[str, Any] = Field(default_factory=dict)


class JobResponse(BaseModel):
    id: str
    evidence_id: str
    technique: str
    status: str
    progress: int = 0
    progress_message: str = ""
    parameters: Dict[str, Any]
    result_path: str | None
    result_sha256: str | None
    artifact_sha256: str | None = None
    runtime_manifest: Dict[str, Any] | None = None
    determinism_profile: str | None = None
    started_at: str | None
    completed_at: str | None
    error_message: str | None
    created_at: str
    gpu_queue_position: int | None = None
    pending_gpu_jobs: int | None = None
    gpu_queue_message: str | None = None


class TechniqueResponse(BaseModel):
    name: str
    supported_types: list[str]
    description: str | None = None
    parameters_schema: Dict[str, Any] | None = None
    available: bool = True
    unavailable_reason: str | None = None


def _serialize_job(job: Any, db: Session | None = None) -> dict:
    """Convert AnalysisJob SQLAlchemy object to JSON-serializable dict."""
    payload = {
        "id": str(job.id),
        "evidence_id": str(job.evidence_id),
        "technique": job.technique,
        "status": job.status,
        "progress": int(job.progress or 0),
        "progress_message": job.progress_message or "",
        "parameters": job.parameters or {},
        "result_path": job.result_path,
        "result_sha256": job.result_sha256,
        "artifact_sha256": job.artifact_sha256,
        "runtime_manifest": job.runtime_manifest or {},
        "determinism_profile": job.determinism_profile,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "error_message": job.error_message,
        "created_at": job.created_at.isoformat() if job.created_at else "",
    }
    if db is not None and job.status == "pending":
        from services.gpu_queue_service import gpu_queue_snapshot, gpu_wait_message, is_gpu_technique

        if is_gpu_technique(job.technique):
            snap = gpu_queue_snapshot(db, job_id=job.id)
            payload["gpu_queue_position"] = snap.get("gpu_queue_position")
            payload["pending_gpu_jobs"] = snap.get("pending_gpu_jobs")
            payload["gpu_queue_message"] = gpu_wait_message(snap)
    return payload


def _job_result_dir(job: Any, settings: Any) -> Path:
    """Return canonical result directory for a completed job."""
    return build_job_result_dir(
        settings.RESULTS_DIR,
        job.evidence.case_id,
        job.evidence_id,
        job.id,
    )


@router.get("/analysis/techniques", response_model=list[TechniqueResponse])
def list_techniques(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all available forensic analysis techniques."""
    service = JobService(db)
    return service.list_techniques()


@router.get("/analysis/imdlbenco/methods")
def list_imdlbenco_methods(
    current_user: User = Depends(get_current_user),
):
    """List IMDL-BenCo hub methods with per-method runtime status."""
    from forensics.imdlbenco.imdlbenco_runtime import list_method_status

    rows = list_method_status()
    if str(current_user.role) != "admin":
        rows = [row for row in rows if row.get("id") not in IMDL_ADMIN_ONLY_METHODS]
    return rows


@router.get("/analysis/audio-spoofing-detectors")
def list_audio_spoofing_detectors(
    current_user: User = Depends(get_current_user),
):
    """Catalog of audio spoofing detectors with per-detector runtime status."""
    from forensics.audio_spoofing.runtime import DETECTOR_CATALOG, detector_runtime_status

    _ = current_user
    rows = []
    for item in DETECTOR_CATALOG:
        ok, reason = detector_runtime_status(item["id"])
        rows.append({**item, "available": ok, "unavailable_reason": reason if not ok else None})
    return rows


@router.get("/analysis/synthetic-image-detectors")
def list_synthetic_image_detectors(
    current_user: User = Depends(get_current_user),
):
    """Catalog of synthetic-image detectors with per-detector runtime status."""
    from forensics.synthetic_image_detection.runtime import DETECTOR_CATALOG, detector_runtime_status

    _ = current_user
    rows = []
    for item in DETECTOR_CATALOG:
        ok, reason = detector_runtime_status(item["id"])
        rows.append({**item, "available": ok, "unavailable_reason": reason if not ok else None})
    return rows


@router.get("/analysis/audio-spoofing-reference-catalog")
def list_audio_spoofing_reference_catalog(
    current_user: User = Depends(get_current_user),
):
    """Return hierarchical audio-spoofing reference-population catalog."""
    from core.audio_spoofing_lr_reference import detector_eer_catalog_metadata, reference_macro_catalog

    _ = current_user
    return {
        "categories": reference_macro_catalog(),
        **detector_eer_catalog_metadata(),
    }


@router.get("/analysis/synthetic-reference-catalog")
def list_synthetic_reference_catalog(
    current_user: User = Depends(get_current_user),
):
    """Return hierarchical synthetic-image reference-population catalog.

    Macro categories (GAN older, diffusion CNN early/modern, diffusion
    transformer, other) group bases and generators so the frontend can render
    a three-level selector. Includes the product default population
    (Transformer + CNN moderna + AIGI Bench Social).
    """
    from core.synthetic_lr_reference import (
        default_reference_population,
        reference_macro_catalog,
    )

    _ = current_user
    return {
        "categories": reference_macro_catalog(),
        "default_reference_items": default_reference_population(),
    }


@router.get("/analysis/provenance-contract")
def list_provenance_contract(
    current_user: User = Depends(get_current_user),
):
    """Matriz de contrato de proveniencia por tecnica (insumos, params, artefatos)."""
    from core.plugin_registry import PluginRegistry

    _ = current_user
    registry = PluginRegistry()
    techniques: dict[str, dict[str, Any] | None] = {}
    for name in registry.PLUGINS:
        techniques[name] = provenance_contract(name)
    return {"schema_version": "1", "techniques": techniques}


@router.post("/analysis", status_code=status.HTTP_201_CREATED)
def submit_job(
    request: SubmitJobRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Submit a forensic analysis job; execution runs in background (thread or Celery)."""
    evidence = get_accessible_evidence(db, request.evidence_id, current_user)
    assert_can_edit_case(db, evidence.case, current_user)
    assert_case_not_closed(evidence.case)
    if str(current_user.role) != "admin":
        if request.technique in ADMIN_ONLY_TECHNIQUES:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Tecnica disponivel apenas para administradores.",
            )
        if (
            request.technique == "imdlbenco"
            and request.parameters.get("method") in IMDL_ADMIN_ONLY_METHODS
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Metodo disponivel apenas para administradores.",
            )
    service = JobService(db)
    job = service.submit_job(
        evidence_id=request.evidence_id,
        technique=request.technique,
        parameters=request.parameters,
        user_id=current_user.id,
    )

    run_job_in_background(job.id)
    db.refresh(job)

    return {
        "job_id": str(job.id),
        "status": job.status,
        "progress": int(job.progress or 0),
        "progress_message": job.progress_message or "",
        "message": "Job submetido com sucesso",
    }


@router.get("/analysis/gpu-queue")
def get_gpu_queue(
    job_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Pending GPU jobs count and optional queue position for a job."""
    from services.gpu_queue_service import gpu_queue_snapshot, gpu_wait_message

    snap = gpu_queue_snapshot(db, job_id=job_id)
    snap["gpu_queue_message"] = gpu_wait_message(snap)
    return snap


@router.get("/analysis/{job_id}", response_model=JobResponse)
def get_job(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get job metadata by ID."""
    service = JobService(db)
    job = service.get_job(job_id)
    return _serialize_job(job, db)


@router.get("/analysis/{job_id}/result")
def get_job_result(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get job result JSON metadata. Returns 409 if job is not completed."""
    service = JobService(db)
    job = service.get_job(job_id)

    if job.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Job ainda nao completado",
        )

    settings = get_settings()
    result_json = _job_result_dir(job, settings) / "result.json"
    if result_json.exists():
        import json
        with open(result_json, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data

    return {
        "job_id": str(job.id),
        "status": job.status,
        "result_path": job.result_path,
        "result_sha256": job.result_sha256,
    }


@router.post("/analysis/{job_id}/reproduce")
def reproduce_analysis_job(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Re-execute a completed job and compare canonical artifact SHA-256."""
    service = JobService(db)
    job = service.get_job(job_id)
    evidence = get_accessible_evidence(db, job.evidence_id, current_user)
    if not evidence:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sem acesso a evidencia deste job",
        )
    return service.reproduce_job(job_id)


@router.get("/analysis/{job_id}/result/file")
def get_job_result_file(
    job_id: uuid.UUID,
    filename: str = "result.json",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Serve a result file (image, json, etc.) from the job result directory."""
    service = JobService(db)
    job = service.get_job(job_id)

    if job.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Job ainda nao completado",
        )

    settings = get_settings()
    file_path = _job_result_dir(job, settings) / filename

    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Arquivo '{filename}' nao encontrado",
        )

    # Security: ensure file is within results dir
    results_dir = Path(settings.RESULTS_DIR).resolve()
    if not file_path.resolve().is_relative_to(results_dir):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso negado",
        )

    media_type = None
    if file_path.suffix.lower() == ".html":
        media_type = "text/html"
    elif file_path.suffix.lower() in (".png", ".jpg", ".jpeg"):
        media_type = f"image/{file_path.suffix.lower().lstrip('.')}"
        if media_type == "image/jpg":
            media_type = "image/jpeg"
    elif file_path.suffix.lower() == ".pdf":
        media_type = "application/pdf"
    elif file_path.suffix.lower() == ".txt":
        media_type = "text/plain; charset=utf-8"
    elif file_path.suffix.lower() == ".json":
        media_type = "application/json"

    return FileResponse(str(file_path), media_type=media_type)


@router.get("/analysis/{job_id}/result/spectrogram-display")
def get_spectrogram_display_data(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Grade decimada do espectrograma (JSON) para re-renderizar paleta no cliente sem recomputar STFT."""
    service = JobService(db)
    job = service.get_job(job_id)

    if job.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Job ainda nao completado",
        )

    settings = get_settings()
    result_dir = _job_result_dir(job, settings)
    results_dir = Path(settings.RESULTS_DIR).resolve()
    if not result_dir.resolve().is_relative_to(results_dir):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado")

    if not has_display_handler(job.technique):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dados de exibicao nao disponiveis para tecnica {job.technique}",
        )

    return JSONResponse(load_display_data(job.technique, result_dir))


@router.get("/analysis/{job_id}/result/audio-plot-data")
def get_audio_plot_data(
    job_id: uuid.UUID,
    panel: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Tracos Plotly serializados para sobreposicao (reter dados para comparacao)."""
    service = JobService(db)
    job = service.get_job(job_id)

    if job.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Job ainda nao completado",
        )

    settings = get_settings()
    result_dir = _job_result_dir(job, settings)
    results_root = Path(settings.RESULTS_DIR).resolve()
    if not result_dir.resolve().is_relative_to(results_root):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado")

    if not has_display_handler(job.technique):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plot data nao disponivel para esta tecnica",
        )

    return JSONResponse(load_display_data(job.technique, result_dir, panel=panel))


@router.post("/analysis/{job_id}/spectrogram/snapshot")
async def upload_spectrogram_snapshot(
    job_id: uuid.UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Recebe PNG do grafico atual (paleta/decimacao do cliente) para salvar como derivado."""
    service = JobService(db)
    job = service.get_job(job_id)

    if job.status != "completed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Job ainda nao completado")

    settings = get_settings()
    result_dir = _job_result_dir(job, settings)
    results_root = Path(settings.RESULTS_DIR).resolve()
    result_dir.mkdir(parents=True, exist_ok=True)
    if not result_dir.resolve().is_relative_to(results_root):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado")

    if not has_snapshot_handler(job.technique):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Snapshot nao disponivel para tecnica {job.technique}",
        )

    content_type = (file.content_type or "").lower()
    if content_type and content_type not in ("image/png", "application/octet-stream"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Arquivo deve ser PNG",
        )

    data = await file.read()
    return store_snapshot(job.technique, result_dir, "spectrogram_snapshot.png", data)


@router.post("/analysis/{job_id}/plot-snapshot")
async def upload_plot_snapshot(
    job_id: uuid.UUID,
    artifact_filename: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Recebe PNG do grafico composto no cliente (overlay multi-evidencia) para custodia."""
    expected_technique = AUDIO_PLOT_SNAPSHOT_FILENAMES.get(artifact_filename)
    if not expected_technique:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"artifact_filename invalido: {artifact_filename}",
        )

    service = JobService(db)
    job = service.get_job(job_id)

    if job.status != "completed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Job ainda nao completado")
    if job.technique != expected_technique:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Snapshot '{artifact_filename}' nao disponivel para tecnica {job.technique}",
        )

    settings = get_settings()
    result_dir = _job_result_dir(job, settings)
    results_root = Path(settings.RESULTS_DIR).resolve()
    result_dir.mkdir(parents=True, exist_ok=True)
    if not result_dir.resolve().is_relative_to(results_root):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado")

    content_type = (file.content_type or "").lower()
    if content_type and content_type not in ("image/png", "application/octet-stream"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Arquivo deve ser PNG",
        )

    data = await file.read()
    return store_snapshot(job.technique, result_dir, artifact_filename, data)


class WaveletNoiseResiduePreviewRequest(BaseModel):
    blocksize: int = Field(default=3, ge=3, le=80)
    thr: int = Field(default=255, ge=0, le=255)
    post: bool = True


@router.post("/analysis/{job_id}/result/wavelet-noise-residue-preview")
def preview_wavelet_noise_residue(
    job_id: uuid.UUID,
    body: WaveletNoiseResiduePreviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Re-apply blocksize/threshold post-processing from cached DWT coefficients (no new DWT)."""
    service = JobService(db)
    job = service.get_job(job_id)
    evidence = get_accessible_evidence(db, job.evidence_id, current_user)
    if not evidence:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sem acesso a evidencia deste job",
        )

    if job.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Job ainda nao completado",
        )

    settings = get_settings()
    result_dir = _job_result_dir(job, settings)
    results_root = Path(settings.RESULTS_DIR).resolve()
    if not result_dir.resolve().is_relative_to(results_root):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado")

    if not has_preview_handler(job.technique):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Preview nao disponivel para tecnica {job.technique}",
        )

    return preview(
        job.technique,
        job,
        result_dir,
        {
            "blocksize": body.blocksize,
            "thr": body.thr,
            "post": body.post,
        },
    )
