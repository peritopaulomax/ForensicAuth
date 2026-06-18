"""Unit tests for evidence upload service and endpoints."""

import io
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from models.case import Case
from models.user import User
from services.evidence_service import EvidenceService, EvidenceUploadError


client = TestClient(app)


@pytest.fixture
def sample_case(db_session, test_user):
    """Create a sample case for testing."""
    case = Case(
        protocol_number="TEST-2026-001",
        title="Caso de Teste",
        description="Descricao do caso de teste",
        created_by=test_user.id,
    )
    db_session.add(case)
    db_session.commit()
    db_session.refresh(case)
    return case


class TestEvidenceService:
    """TU-EVD-001 to TU-EVD-005"""

    def test_upload_jpeg(self, db_session, sample_case, test_user):
        """TU-EVD-001: Upload a JPEG file successfully."""
        service = EvidenceService(db_session)
        file_content = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 100
        file_obj = io.BytesIO(file_content)

        evidence = service.upload_evidence(
            case_id=sample_case.id,
            filename="photo.jpg",
            mime_type="image/jpeg",
            file_obj=file_obj,
            uploaded_by=test_user.id,
        )

        assert evidence.file_type == "imagem"
        assert evidence.original_filename == "photo.jpg"
        assert evidence.file_size == len(file_content)
        assert len(evidence.sha256) == 64
        assert evidence.case_id == sample_case.id

    def test_upload_pdf(self, db_session, sample_case, test_user):
        """TU-EVD-002: Upload a PDF file successfully."""
        service = EvidenceService(db_session)
        file_content = b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n>>\nendobj\n"
        file_obj = io.BytesIO(file_content)

        evidence = service.upload_evidence(
            case_id=sample_case.id,
            filename="document.pdf",
            mime_type="application/pdf",
            file_obj=file_obj,
            uploaded_by=test_user.id,
        )

        assert evidence.file_type == "pdf"
        assert evidence.mime_type == "application/pdf"

    def test_reject_empty_file(self, db_session, sample_case, test_user):
        """TU-EVD-003: Reject empty file."""
        service = EvidenceService(db_session)
        file_obj = io.BytesIO(b"")

        with pytest.raises(EvidenceUploadError, match="Arquivo vazio"):
            service.upload_evidence(
                case_id=sample_case.id,
                filename="empty.jpg",
                mime_type="image/jpeg",
                file_obj=file_obj,
                uploaded_by=test_user.id,
            )

    def test_reject_duplicate_sha256(self, db_session, sample_case, test_user):
        """TU-EVD-004: Reject duplicate file in same case."""
        service = EvidenceService(db_session)
        file_content = b"\xff\xd8\xff\xe0\x00\x10JFIF duplicate content"

        # First upload
        file_obj1 = io.BytesIO(file_content)
        service.upload_evidence(
            case_id=sample_case.id,
            filename="file1.jpg",
            mime_type="image/jpeg",
            file_obj=file_obj1,
            uploaded_by=test_user.id,
        )

        # Second upload with same content
        file_obj2 = io.BytesIO(file_content)
        with pytest.raises(EvidenceUploadError, match="identico ja consta"):
            service.upload_evidence(
                case_id=sample_case.id,
                filename="file2.jpg",
                mime_type="image/jpeg",
                file_obj=file_obj2,
                uploaded_by=test_user.id,
            )

    def test_allow_reupload_after_soft_delete(self, db_session, sample_case, test_user):
        """Re-upload permitido quando unica copia anterior foi excluida (soft-delete)."""
        service = EvidenceService(db_session)
        file_content = b"\xff\xd8\xff\xe0\x00\x10JFIF reupload after delete"
        file_obj1 = io.BytesIO(file_content)
        evidence = service.upload_evidence(
            case_id=sample_case.id,
            filename="once.jpg",
            mime_type="image/jpeg",
            file_obj=file_obj1,
            uploaded_by=test_user.id,
        )
        service.delete_evidence(evidence.id, deleted_by=test_user.id)

        file_obj2 = io.BytesIO(file_content)
        again = service.upload_evidence(
            case_id=sample_case.id,
            filename="again.jpg",
            mime_type="image/jpeg",
            file_obj=file_obj2,
            uploaded_by=test_user.id,
        )
        assert again.id != evidence.id
        assert again.sha256 == evidence.sha256
        assert again.deleted_at is None

    def test_duplicate_error_names_active_evidence(self, db_session, sample_case, test_user):
        service = EvidenceService(db_session)
        file_content = b"\xff\xd8\xff\xe0\x00\x10JFIF named duplicate"
        service.upload_evidence(
            case_id=sample_case.id,
            filename="visible.jpg",
            mime_type="image/jpeg",
            file_obj=io.BytesIO(file_content),
            uploaded_by=test_user.id,
        )
        with pytest.raises(EvidenceUploadError, match="visible.jpg"):
            service.upload_evidence(
                case_id=sample_case.id,
                filename="other.jpg",
                mime_type="image/jpeg",
                file_obj=io.BytesIO(file_content),
                uploaded_by=test_user.id,
            )

    def test_reject_unsupported_type(self, db_session, sample_case, test_user):
        """TU-EVD-005: Reject unsupported file type."""
        service = EvidenceService(db_session)
        file_obj = io.BytesIO(b"some content")

        with pytest.raises(EvidenceUploadError, match="nao suportado"):
            service.upload_evidence(
                case_id=sample_case.id,
                filename="archive.zip",
                mime_type="application/zip",
                file_obj=file_obj,
                uploaded_by=test_user.id,
            )


class TestEvidenceEndpoint:
    """TU-EVD-006: Upload endpoint rejects unauthenticated requests."""

    def test_upload_without_auth(self, db_session, sample_case):
        """Reject upload without authentication."""
        file_content = b"\xff\xd8\xff\xe0\x00\x10JFIF"
        response = client.post(
            "/api/v1/evidences/upload",
            data={"case_id": str(sample_case.id)},
            files={"file": ("test.jpg", io.BytesIO(file_content), "image/jpeg")},
        )
        assert response.status_code == 401
