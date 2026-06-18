"""PRNU fingerprint storage — derived evidences with custody chain."""

from __future__ import annotations

import json
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.config import get_settings
from core.plugins.prnu_adapter import PRNUAdapter
from models.evidence import Evidence
from services.case_access import get_accessible_case, get_accessible_evidence
from services.derivative_service import DerivativeSaveError, DerivativeService
from services.evidence_classification import is_reference, reference_group_label


def _is_prnu_fingerprint(evidence: Evidence) -> bool:
    meta = evidence.extra_metadata or {}
    return meta.get("origin") == "derived" and meta.get("artifact_role") == "prnu_fingerprint"


def _sanitize_rotulo(rotulo: str) -> str:
    cleaned = "".join(c if c.isalnum() or c in "-_" else "-" for c in rotulo.strip())
    return cleaned.strip("-_") or "grupo"


def _next_fingerprint_label(db: Session, case_id: uuid.UUID, rotulo: str) -> str:
    """Auto-name: PRNU-{rotulo}-{seq:03d} per case."""
    safe = _sanitize_rotulo(rotulo)
    prefix = f"PRNU-{safe}-"
    seq = 0
    evidences = (
        db.query(Evidence)
        .filter(Evidence.case_id == case_id, Evidence.deleted_at.is_(None))
        .all()
    )
    for ev in evidences:
        if not _is_prnu_fingerprint(ev):
            continue
        meta = ev.extra_metadata or {}
        existing = str(meta.get("label") or ev.original_filename or "")
        if existing.startswith(prefix):
            suffix = existing[len(prefix) :].split(".")[0]
            if suffix.isdigit():
                seq = max(seq, int(suffix))
    return f"{prefix}{seq + 1:03d}"


def _legacy_meta_dir(case_id: uuid.UUID) -> Path:
    settings = get_settings()
    return Path(settings.MODELS_DIR) / "prnu" / "fingerprints" / str(case_id)


def list_fingerprints(db: Session, case_id: uuid.UUID, user) -> List[Dict[str, Any]]:
    get_accessible_case(db, case_id, user)
    items: List[Dict[str, Any]] = []

    evidences = (
        db.query(Evidence)
        .filter(Evidence.case_id == case_id, Evidence.deleted_at.is_(None))
        .order_by(Evidence.created_at.desc())
        .all()
    )
    for ev in evidences:
        if not _is_prnu_fingerprint(ev):
            continue
        meta = ev.extra_metadata or {}
        items.append(
            {
                "id": str(ev.id),
                "derivative_evidence_id": str(ev.id),
                "case_id": str(case_id),
                "label": meta.get("label") or ev.original_filename,
                "reference_group_label": meta.get("reference_group_label"),
                "sigma": meta.get("sigma") or meta.get("parameters", {}).get("sigma"),
                "images_used": meta.get("images_used"),
                "shape": meta.get("shape"),
                "evidence_ids": meta.get("parent_evidence_ids") or [],
                "fingerprint_path": ev.file_path,
                "sha256": ev.sha256,
                "created_at": ev.created_at.isoformat() if ev.created_at else "",
                "created_by": str(ev.uploaded_by),
                "exists": Path(ev.file_path).exists(),
            }
        )

    # Fingerprints em models/ sem derivado correspondente na base
    legacy_dir = _legacy_meta_dir(case_id)
    known_ids = {item["id"] for item in items}
    if legacy_dir.exists():
        for meta_path in legacy_dir.glob("*.json"):
            try:
                with open(meta_path, encoding="utf-8") as f:
                    meta = json.load(f)
            except (OSError, json.JSONDecodeError):
                continue
            fp_id = meta.get("id") or meta_path.stem
            if fp_id in known_ids:
                continue
            npy = legacy_dir / f"{fp_id}.npy"
            meta["exists"] = npy.exists()
            meta["legacy"] = True
            items.append(meta)

    return items


def create_fingerprint(
    db: Session,
    case_id: uuid.UUID,
    evidence_ids: List[uuid.UUID],
    label: str,
    sigma: float,
    user,
    group_label: str | None = None,
) -> Dict[str, Any]:
    get_accessible_case(db, case_id, user)
    if not evidence_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Envie e selecione ao menos uma imagem de referencia",
        )
    if len(evidence_ids) > 50:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Maximo de 50 imagens por fingerprint",
        )

    image_paths: List[str] = []
    used_meta: List[Dict[str, str]] = []
    ref_labels: set[str] = set()
    for ev_id in evidence_ids:
        evidence = get_accessible_evidence(db, ev_id, user)
        if evidence.case_id != case_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Evidencia {ev_id} nao pertence ao caso",
            )
        if evidence.file_type != "imagem":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Evidencia {evidence.original_filename} nao e imagem",
            )
        if not is_reference(evidence):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"{evidence.original_filename} nao e imagem de referencia PRNU",
            )
        ref_labels.add(reference_group_label(evidence))
        image_paths.append(evidence.file_path)
        used_meta.append(
            {
                "evidence_id": str(evidence.id),
                "original_filename": evidence.original_filename,
            }
        )

    if len(ref_labels) > 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Selecione imagens de referencia do mesmo rotulo de grupo",
        )

    rotulo = (group_label or "").strip() or (next(iter(ref_labels)) if ref_labels else "")
    if not rotulo:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Informe o rotulo do grupo de referencia",
        )
    if ref_labels and rotulo not in ref_labels:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Imagens selecionadas pertencem ao grupo '{next(iter(ref_labels))}', nao a '{rotulo}'",
        )

    display_label = label.strip() or _next_fingerprint_label(db, case_id, rotulo)

    with tempfile.TemporaryDirectory(prefix="prnu_fp_") as tmp:
        tmp_npy = Path(tmp) / "fingerprint.npy"
        adapter = PRNUAdapter()
        gen = adapter.generate_fingerprint(image_paths, str(tmp_npy), sigma=sigma)
        if not gen.get("success"):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=gen.get("error", "Falha ao gerar fingerprint"),
            )

        deriv_service = DerivativeService(db)
        try:
            derivative = deriv_service.save_prnu_fingerprint(
                case_id=case_id,
                npy_source_path=tmp_npy,
                parent_evidence_ids=evidence_ids,
                user_id=user.id,
                label=display_label,
                sigma=sigma,
                images_used=int(gen.get("images_used", len(image_paths))),
                shape=gen.get("shape"),
                reference_group_label=rotulo,
            )
        except DerivativeSaveError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(exc),
            ) from exc

    return {
        "id": str(derivative.id),
        "derivative_evidence_id": str(derivative.id),
        "case_id": str(case_id),
        "label": display_label,
        "reference_group_label": rotulo,
        "sigma": sigma,
        "images_used": gen.get("images_used", len(image_paths)),
        "shape": gen.get("shape"),
        "evidence_ids": [str(e) for e in evidence_ids],
        "evidences": used_meta,
        "fingerprint_path": derivative.file_path,
        "sha256": derivative.sha256,
        "created_at": derivative.created_at.isoformat() if derivative.created_at else "",
        "created_by": str(user.id),
        "exists": True,
        "saved_as_derivative": True,
    }


def resolve_fingerprint_path(
    db: Session,
    case_id: uuid.UUID,
    fingerprint_id: str,
    user=None,
) -> Path:
    """Resolve fingerprint file from derivative evidence id (or legacy models path)."""
    if user is not None:
        get_accessible_case(db, case_id, user)
    try:
        fp_uuid = uuid.UUID(str(fingerprint_id))
    except ValueError:
        fp_uuid = None

    if fp_uuid:
        ev = (
            db.query(Evidence)
            .filter(
                Evidence.id == fp_uuid,
                Evidence.case_id == case_id,
                Evidence.deleted_at.is_(None),
            )
            .first()
        )
        if ev and _is_prnu_fingerprint(ev):
            path = Path(ev.file_path)
            if path.exists():
                return path

    legacy = _legacy_meta_dir(case_id) / f"{fingerprint_id}.npy"
    if legacy.exists():
        return legacy

    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail=f"Fingerprint '{fingerprint_id}' nao encontrado para o caso",
    )
