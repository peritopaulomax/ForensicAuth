"""Evidence upload service — handles file storage, SHA-256 hashing, and metadata."""

import hashlib
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO, Dict

from sqlalchemy.orm import Session

from app.config import get_settings
from models.case import Case
from models.evidence import Evidence
from services.case_access import assert_case_not_closed
from services.custody_service import CustodyService
from services.audio_evidence_metadata import AUDIO_TECHNICAL_KEY, probe_audio_for_upload
from services.evidence_classification import is_derived, is_reference, reference_technique

# Supported MIME type → evidence_type mapping
MIME_TYPE_MAP = {
    "image/jpeg": "imagem",
    "image/png": "imagem",
    "image/tiff": "imagem",
    "image/bmp": "imagem",
    "image/webp": "imagem",
    "audio/mpeg": "audio",
    "audio/mp3": "audio",
    "audio/wav": "audio",
    "audio/x-wav": "audio",
    "audio/ogg": "audio",
    "audio/opus": "audio",
    "video/mp4": "video",
    "video/avi": "video",
    "video/x-msvideo": "video",
    "video/mpeg": "video",
    "application/pdf": "pdf",
}

MAX_FILE_SIZE = 500 * 1024 * 1024  # 500 MB


class EvidenceUploadError(Exception):
    """Raised when evidence upload fails validation or storage."""

    pass


class EvidenceService:
    """Service for uploading and managing evidence files."""

    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    def _compute_sha256(self, file_obj: BinaryIO) -> str:
        """Compute SHA-256 hash of a file-like object."""
        file_obj.seek(0)
        sha256 = hashlib.sha256()
        for chunk in iter(lambda: file_obj.read(8192), b""):
            sha256.update(chunk)
        file_obj.seek(0)
        return sha256.hexdigest()

    def _infer_file_type(self, mime_type: str | None, filename: str) -> str:
        """Infer evidence type from MIME type or filename extension."""
        if mime_type:
            mapped = MIME_TYPE_MAP.get(mime_type.lower())
            if mapped:
                return mapped
        # Fallback to extension
        ext = Path(filename).suffix.lower()
        if ext in (".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp", ".webp"):
            return "imagem"
        if ext in (".mp3", ".wav", ".ogg", ".opus", ".oga"):
            return "audio"
        if ext in (".mp4", ".avi", ".mpeg", ".mpg", ".mov"):
            return "video"
        if ext == ".pdf":
            return "pdf"
        raise EvidenceUploadError(f"Tipo de arquivo nao suportado: {ext or mime_type}")

    @staticmethod
    def _duplicate_role_label(evidence: Evidence) -> str:
        if is_derived(evidence):
            return "derivado"
        if is_reference(evidence):
            tech = reference_technique(evidence) or "referencia"
            return f"referencia ({tech})"
        return "evidencia"

    def _raise_if_active_duplicate(self, case_id: uuid.UUID, sha256: str) -> None:
        existing = (
            self.db.query(Evidence)
            .filter(
                Evidence.case_id == case_id,
                Evidence.sha256 == sha256,
                Evidence.deleted_at.is_(None),
            )
            .first()
        )
        if not existing:
            return
        role = self._duplicate_role_label(existing)
        raise EvidenceUploadError(
            f"Arquivo identico ja consta neste caso como {role}: {existing.original_filename}."
        )

    def upload_evidence(
        self,
        case_id: uuid.UUID,
        filename: str,
        mime_type: str | None,
        file_obj: BinaryIO,
        uploaded_by: uuid.UUID,
        extra_metadata: Dict[str, Any] | None = None,
    ) -> Evidence:
        """Upload a new evidence file.

        Args:
            case_id: UUID of the case this evidence belongs to.
            filename: Original filename.
            mime_type: MIME type of the file (optional).
            file_obj: File-like object (must be seekable).
            uploaded_by: UUID of the uploading user.

        Returns:
            The created Evidence record.
        """
        case = self.db.query(Case).filter(Case.id == case_id).first()
        if case:
            assert_case_not_closed(case)

        # Validate file size
        file_obj.seek(0, 2)  # Seek to end
        file_size = file_obj.tell()
        file_obj.seek(0)

        if file_size == 0:
            raise EvidenceUploadError("Arquivo vazio nao permitido")
        if file_size > MAX_FILE_SIZE:
            raise EvidenceUploadError(
                f"Arquivo excede o tamanho maximo de {MAX_FILE_SIZE // (1024 * 1024)} MB"
            )

        # Infer type
        file_type = self._infer_file_type(mime_type, filename)

        # Compute SHA-256
        sha256 = self._compute_sha256(file_obj)

        self._raise_if_active_duplicate(case_id, sha256)

        # Save to disk
        evidence_id = uuid.uuid4()
        ext = Path(filename).suffix
        stored_filename = f"{evidence_id}{ext}"
        upload_dir = Path(self.settings.UPLOAD_DIR)
        file_path = upload_dir / stored_filename

        file_obj.seek(0)
        with open(file_path, "wb") as dest:
            shutil.copyfileobj(file_obj, dest)

        upload_metadata = dict(extra_metadata or {})
        if file_type == "audio":
            try:
                audio_technical = probe_audio_for_upload(str(file_path))
                if audio_technical:
                    upload_metadata[AUDIO_TECHNICAL_KEY] = audio_technical
            except Exception:
                pass

        # Create DB record
        evidence = Evidence(
            id=evidence_id,
            case_id=case_id,
            filename=stored_filename,
            original_filename=filename,
            file_path=str(file_path),
            file_size=file_size,
            file_type=file_type,
            mime_type=mime_type,
            sha256=sha256,
            extra_metadata=upload_metadata,
            uploaded_by=uploaded_by,
        )
        self.db.add(evidence)
        self.db.commit()
        self.db.refresh(evidence)

        from services.peritus_va_materializer import mark_peritus_binding_modified

        case_row = self.db.query(Case).filter(Case.id == case_id).first()
        if case_row and getattr(case_row, "storage_mode", "va") == "peritus":
            mark_peritus_binding_modified(self.settings, case_id)

        custody = CustodyService(self.db)
        custody.create_record(
            record_type="evidence_upload",
            case_id=case_id,
            evidence_id=evidence.id,
            user_id=uploaded_by,
            sha256_input=sha256,
            sha256_output=sha256,
            details={
                "provenance_schema_version": "1",
                "original_filename": filename,
                "file_type": file_type,
                "file_size": file_size,
                "mime_type": mime_type,
                "sha256": sha256,
                "evidence_id": str(evidence.id),
                **upload_metadata,
            },
        )

        return evidence

    def delete_evidence(self, evidence_id: uuid.UUID, deleted_by: uuid.UUID) -> None:
        """Soft-delete evidence after logging to custody chain and removing the file."""
        evidence = (
            self.db.query(Evidence)
            .filter(Evidence.id == evidence_id, Evidence.deleted_at.is_(None))
            .first()
        )
        if not evidence:
            raise EvidenceUploadError("Evidencia nao encontrada")

        custody = CustodyService(self.db)
        custody.create_record(
            record_type="evidence_deleted",
            case_id=evidence.case_id,
            evidence_id=evidence.id,
            user_id=deleted_by,
            sha256_input=evidence.sha256,
            details={
                "provenance_schema_version": "1",
                "evidence_id": str(evidence.id),
                "original_filename": evidence.original_filename,
                "file_type": evidence.file_type,
                "file_size": evidence.file_size,
                "sha256": evidence.sha256,
                "file_path": evidence.file_path,
            },
        )

        file_path = Path(evidence.file_path)
        if file_path.exists():
            file_path.unlink()

        evidence.deleted_at = datetime.now(timezone.utc).replace(tzinfo=None)
        evidence.deleted_by = deleted_by
        self.db.commit()
