"""Materializa arquivos Peritus importados como evidencias ForensicAuth (upload + derivados)."""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from models.evidence import Evidence
from models.user import User
from services.custody_service import CustodyService
from services.peritus_file_meta import (
    build_xml_path_index,
    guess_mime,
    infer_file_type,
)
from services.peritus_xml import PERITUS_XML_NAME

VA_EVIDENCE_TYPES = frozenset({"imagem", "audio", "video", "pdf"})


def _sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _parse_uuid(value: str | None) -> uuid.UUID | None:
    if not value:
        return None
    try:
        return uuid.UUID(str(value))
    except ValueError:
        return None


def materialize_peritus_file(
    db: Session,
    *,
    case_id: uuid.UUID,
    workspace: Path,
    xml_bytes: bytes,
    relative_path: str,
    imported_by: User,
    custody: CustodyService | None = None,
    record_custody: bool = False,
) -> dict[str, Any] | None:
    """Materializa um unico arquivo Peritus para analise VA (lazy, sob demanda)."""
    rel = relative_path.replace("\\", "/").lstrip("/")
    if rel == PERITUS_XML_NAME or ".." in rel.split("/"):
        return None

    file_path = workspace / rel
    if not file_path.is_file():
        return None

    index = build_xml_path_index(xml_bytes)
    meta = index.get(rel, {})
    filename = file_path.name
    mime = meta.get("mime_type") or guess_mime(filename)
    file_type = infer_file_type(filename, mime)
    if file_type not in VA_EVIDENCE_TYPES:
        return None

    sha256 = meta.get("sha256") or _sha256_path(file_path)
    is_derived = bool(
        meta.get("is_derived")
        or meta.get("kind") == "derived"
        or rel.startswith("derived-files/")
    )

    existing = (
        db.query(Evidence)
        .filter(
            Evidence.case_id == case_id,
            Evidence.sha256 == sha256,
            Evidence.deleted_at.is_(None),
        )
        .first()
    )
    if existing:
        return {
            "evidence_id": str(existing.id),
            "path": rel,
            "created": False,
            "file_type": file_type,
        }

    custody = custody or CustodyService(db)
    evidence_id = _parse_uuid(meta.get("peritus_uuid")) or uuid.uuid4()
    if db.query(Evidence).filter(Evidence.id == evidence_id).first():
        evidence_id = uuid.uuid4()

    extra: dict[str, Any] = {
        "origin": "derived" if is_derived else "upload",
        "peritus_import": True,
        "peritus_path": rel,
        "peritus_uuid": meta.get("peritus_uuid"),
        "storage_kind": "derivative" if is_derived else "upload",
        "peritus_lazy_materialized": True,
    }
    if is_derived:
        extra["provenance_schema_version"] = "1"
        extra["provenance"] = {
            "provenance_schema_version": "1",
            "note": "Derivado importado do Peritus; cadeia original no peritusCase.xml",
            "peritus_path": rel,
        }
        extra["technique"] = "peritus:imported"
        extra["derivation_step"] = "imported"

    evidence = Evidence(
        id=evidence_id,
        case_id=case_id,
        filename=filename,
        original_filename=filename,
        file_path=str(file_path.resolve()),
        file_size=file_path.stat().st_size,
        file_type=file_type,
        mime_type=mime,
        sha256=sha256,
        extra_metadata=extra,
        uploaded_by=imported_by.id,
    )
    db.add(evidence)
    db.flush()

    if record_custody:
        if is_derived:
            custody.create_record(
                record_type="derivative_saved",
                case_id=case_id,
                evidence_id=evidence.id,
                user_id=imported_by.id,
                sha256_input=None,
                sha256_output=sha256,
                details={
                    "peritus_import": True,
                    "peritus_path": rel,
                    "source": "peritus",
                },
                commit=False,
            )
        else:
            custody.create_record(
                record_type="evidence_upload",
                case_id=case_id,
                evidence_id=evidence.id,
                user_id=imported_by.id,
                sha256_output=sha256,
                details={
                    "peritus_import": True,
                    "peritus_path": rel,
                    "original_filename": filename,
                    "file_type": file_type,
                },
                commit=False,
            )

    return {
        "evidence_id": str(evidence.id),
        "path": rel,
        "created": True,
        "file_type": file_type,
    }


def materialize_peritus_workspace(
    db: Session,
    *,
    case_id: uuid.UUID,
    workspace: Path,
    xml_bytes: bytes,
    imported_by: User,
    custody: CustodyService | None = None,
) -> dict[str, Any]:
    """
    Cria registros Evidence apontando para arquivos no workspace Peritus.
    A partir daqui o caso opera como ForensicAuth padrao (analises, derivados, custodia).
    """
    custody = custody or CustodyService(db)
    index = build_xml_path_index(xml_bytes)
    uploads = 0
    derivatives = 0
    skipped = 0
    path_to_evidence_id: dict[str, str] = {}

    for file_path in sorted(workspace.rglob("*")):
        if not file_path.is_file():
            continue
        rel = file_path.relative_to(workspace).as_posix()
        if rel == PERITUS_XML_NAME:
            continue

        meta = index.get(rel, {})
        filename = file_path.name
        mime = meta.get("mime_type") or guess_mime(filename)
        file_type = infer_file_type(filename, mime)
        if file_type not in VA_EVIDENCE_TYPES:
            skipped += 1
            continue

        sha256 = meta.get("sha256") or _sha256_path(file_path)
        is_derived = bool(
            meta.get("is_derived")
            or meta.get("kind") == "derived"
            or rel.startswith("derived-files/")
        )

        existing = (
            db.query(Evidence)
            .filter(
                Evidence.case_id == case_id,
                Evidence.sha256 == sha256,
                Evidence.deleted_at.is_(None),
            )
            .first()
        )
        if existing:
            path_to_evidence_id[rel] = str(existing.id)
            continue

        evidence_id = _parse_uuid(meta.get("peritus_uuid")) or uuid.uuid4()
        if db.query(Evidence).filter(Evidence.id == evidence_id).first():
            evidence_id = uuid.uuid4()

        extra: dict[str, Any] = {
            "origin": "derived" if is_derived else "upload",
            "peritus_import": True,
            "peritus_path": rel,
            "peritus_uuid": meta.get("peritus_uuid"),
            "storage_kind": "derivative" if is_derived else "upload",
        }
        if is_derived:
            extra["provenance_schema_version"] = "1"
            extra["provenance"] = {
                "provenance_schema_version": "1",
                "note": "Derivado importado do Peritus; cadeia original no peritusCase.xml",
                "peritus_path": rel,
            }
            extra["technique"] = "peritus:imported"
            extra["derivation_step"] = "imported"

        evidence = Evidence(
            id=evidence_id,
            case_id=case_id,
            filename=filename,
            original_filename=filename,
            file_path=str(file_path.resolve()),
            file_size=file_path.stat().st_size,
            file_type=file_type,
            mime_type=mime,
            sha256=sha256,
            extra_metadata=extra,
            uploaded_by=imported_by.id,
        )
        db.add(evidence)
        db.flush()

        path_to_evidence_id[rel] = str(evidence.id)

        if is_derived:
            derivatives += 1
            custody.create_record(
                record_type="derivative_saved",
                case_id=case_id,
                evidence_id=evidence.id,
                user_id=imported_by.id,
                sha256_input=None,
                sha256_output=sha256,
                details={
                    "peritus_import": True,
                    "peritus_path": rel,
                    "source": "peritus",
                },
                commit=False,
            )
        else:
            uploads += 1
            custody.create_record(
                record_type="evidence_upload",
                case_id=case_id,
                evidence_id=evidence.id,
                user_id=imported_by.id,
                sha256_output=sha256,
                details={
                    "peritus_import": True,
                    "peritus_path": rel,
                    "original_filename": filename,
                    "file_type": file_type,
                },
                commit=False,
            )

    return {
        "uploads_materialized": uploads,
        "derivatives_materialized": derivatives,
        "skipped_unsupported": skipped,
        "path_to_evidence_id": path_to_evidence_id,
    }


def mark_peritus_binding_modified(settings: Any, case_id: uuid.UUID) -> None:
    from services.peritus_bridge_service import load_binding, save_binding

    binding = load_binding(settings, case_id)
    if not binding:
        return
    if not binding.get("modified"):
        binding["modified"] = True
        save_binding(settings, case_id, binding)
