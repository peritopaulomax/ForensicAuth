"""Registro na cadeia de custodia de cada arquivo do pacote Peritus importado."""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from models.user import User
from services.custody_service import CustodyService
from services.peritus_file_meta import (
    build_xml_path_index,
    guess_mime,
    infer_file_type,
    peritus_folder_label,
)
from services.peritus_xml import PERITUS_XML_NAME


def _sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def register_peritus_files_in_custody(
    db: Session,
    *,
    case_id: uuid.UUID,
    workspace: Path,
    xml_bytes: bytes,
    xml_sha256: str,
    zip_sha256: str,
    imported_by: User,
    custody: CustodyService | None = None,
) -> dict[str, Any]:
    """
    Cria um registro de custodia por arquivo do workspace Peritus (apos case_imported_peritus).
    Nao cria Evidence VA — apenas encadeia cada artefato importado para auditoria forense.
    """
    custody = custody or CustodyService(db)
    index = build_xml_path_index(xml_bytes)
    uploads = 0
    derived = 0
    manifest = 0

    for file_path in sorted(workspace.rglob("*")):
        if not file_path.is_file():
            continue

        rel = file_path.relative_to(workspace).as_posix()
        meta = index.get(rel, {})
        filename = file_path.name
        mime = meta.get("mime_type") or guess_mime(filename)
        file_type = infer_file_type(filename, mime)
        folder = peritus_folder_label(rel)
        sha256 = meta.get("sha256") or _sha256_path(file_path)
        is_xml = rel == PERITUS_XML_NAME
        is_derived = bool(
            not is_xml
            and (
                meta.get("is_derived")
                or meta.get("kind") == "derived"
                or rel.startswith("derived-files/")
            )
        )

        if is_xml:
            manifest += 1
        elif is_derived:
            derived += 1
        else:
            uploads += 1

        custody.create_record(
            record_type="peritus_file_imported",
            case_id=case_id,
            user_id=imported_by.id,
            sha256_input=zip_sha256 if not is_xml else None,
            sha256_output=sha256,
            details={
                "source": "peritus",
                "peritus_import": True,
                "peritus_chain_anchor": xml_sha256,
                "original_zip_sha256": zip_sha256,
                "original_xml_sha256": xml_sha256,
                "peritus_path": rel,
                "original_filename": filename,
                "folder": folder,
                "file_type": file_type,
                "mime_type": mime,
                "is_derived": is_derived,
                "is_manifest": is_xml,
                "peritus_uuid": meta.get("peritus_uuid"),
                "note": (
                    "Arquivo do pacote Peritus importado; nao e evidencia VA ordinaria, "
                    "mas consta na cadeia para rastreabilidade forense."
                ),
            },
            commit=False,
        )

    return {
        "files_registered": uploads + derived + manifest,
        "uploads_registered": uploads,
        "derived_registered": derived,
        "manifest_registered": manifest,
    }
