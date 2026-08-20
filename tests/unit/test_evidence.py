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


class TestEvidenceBatchDeletion:
    """Exclusao em lote com cascade opcional para derivados exclusivos."""

    def _derivative(self, db_session, case, user, filename, parent_ids):
        from models.evidence import Evidence

        evidence = Evidence(
            id=uuid.uuid4(),
            case_id=case.id,
            filename=filename,
            original_filename=filename,
            file_path=f"/tmp/{filename}",
            file_size=10,
            file_type="imagem",
            mime_type="image/png",
            sha256=uuid.uuid4().hex + uuid.uuid4().hex[:32],
            uploaded_by=user.id,
            extra_metadata={
                "origin": "derived",
                "technique": "ela",
                "parent_inputs": [
                    {"evidence_id": str(pid), "role": "questioned"} for pid in parent_ids
                ],
            },
        )
        db_session.add(evidence)
        db_session.commit()
        db_session.refresh(evidence)
        return evidence

    def _upload(self, db_session, case, user, filename, payload):
        return EvidenceService(db_session).upload_evidence(
            case_id=case.id,
            filename=filename,
            mime_type="image/jpeg",
            file_obj=io.BytesIO(payload),
            uploaded_by=user.id,
        )

    def test_cascade_removes_exclusive_dependent(self, db_session, sample_case, test_user):
        service = EvidenceService(db_session)
        parent = self._upload(db_session, sample_case, test_user, "q.jpg", b"\xff\xd8\xff\xe0A")
        derivative = self._derivative(db_session, sample_case, test_user, "ela.png", [parent.id])

        result = service.delete_evidence_batch(
            case_id=sample_case.id,
            evidence_ids=[parent.id],
            deleted_by=test_user.id,
            include_dependent_derivatives=True,
        )

        assert result["deleted"] == [str(parent.id)]
        assert result["dependents_deleted"] == [str(derivative.id)]
        assert result["failed"] == []
        db_session.refresh(derivative)
        assert derivative.deleted_at is not None

    def test_without_cascade_dependent_survives(self, db_session, sample_case, test_user):
        service = EvidenceService(db_session)
        parent = self._upload(db_session, sample_case, test_user, "q.jpg", b"\xff\xd8\xff\xe0B")
        derivative = self._derivative(db_session, sample_case, test_user, "ela.png", [parent.id])

        result = service.delete_evidence_batch(
            case_id=sample_case.id,
            evidence_ids=[parent.id],
            deleted_by=test_user.id,
            include_dependent_derivatives=False,
        )

        assert result["dependents_deleted"] == []
        db_session.refresh(derivative)
        assert derivative.deleted_at is None

    def test_cascade_preserves_shared_dependent(self, db_session, sample_case, test_user):
        service = EvidenceService(db_session)
        questioned = self._upload(db_session, sample_case, test_user, "q.jpg", b"\xff\xd8\xff\xe0C")
        reference = self._upload(db_session, sample_case, test_user, "r.jpg", b"\xff\xd8\xff\xe0D")
        derivative = self._derivative(
            db_session, sample_case, test_user, "prnu.html", [questioned.id, reference.id]
        )

        result = service.delete_evidence_batch(
            case_id=sample_case.id,
            evidence_ids=[questioned.id],
            deleted_by=test_user.id,
            include_dependent_derivatives=True,
        )

        assert result["dependents_deleted"] == []
        assert len(result["retained_dependents"]) == 1
        assert result["retained_dependents"][0]["retained_parents"] == ["r.jpg"]
        db_session.refresh(derivative)
        assert derivative.deleted_at is None

    def test_partial_failure_does_not_abort_batch(self, db_session, sample_case, test_user):
        service = EvidenceService(db_session)
        valid = self._upload(db_session, sample_case, test_user, "q.jpg", b"\xff\xd8\xff\xe0E")
        missing = uuid.uuid4()

        result = service.delete_evidence_batch(
            case_id=sample_case.id,
            evidence_ids=[missing, valid.id],
            deleted_by=test_user.id,
            include_dependent_derivatives=False,
        )

        assert result["deleted"] == [str(valid.id)]
        assert [f["evidence_id"] for f in result["failed"]] == [str(missing)]
        db_session.refresh(valid)
        assert valid.deleted_at is not None


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
