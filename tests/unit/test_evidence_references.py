"""Tests for reference vs case evidence separation."""

import io
import uuid

import pytest

from models.evidence import Evidence
from services.evidence_classification import (
    group_references,
    is_case_evidence,
    is_reference,
    reference_display_label,
)


def _jpeg_bytes() -> bytes:
    return b"\xff\xd8\xff\xe0\x00\x10JFIF" + uuid.uuid4().bytes + b"\x00" * 80


class TestEvidenceClassification:
    def test_reference_flags(self, db_session, sample_case, test_user):
        ref = Evidence(
            id=uuid.uuid4(),
            case_id=sample_case.id,
            filename="r.jpg",
            original_filename="r.jpg",
            file_path="/uploads/r.jpg",
            file_size=100,
            file_type="imagem",
            sha256="a" * 64,
            extra_metadata={
                "is_reference": True,
                "reference_technique": "prnu",
                "reference_group_label": "D70",
            },
            uploaded_by=test_user.id,
        )
        assert is_reference(ref)
        assert not is_case_evidence(ref)

    def test_legacy_prnu_reference(self, db_session, sample_case, test_user):
        ref = Evidence(
            id=uuid.uuid4(),
            case_id=sample_case.id,
            filename="legacy.jpg",
            original_filename="legacy.jpg",
            file_path="/uploads/legacy.jpg",
            file_size=100,
            file_type="imagem",
            sha256="c" * 64,
            extra_metadata={"prnu_reference": True, "for_technique": "prnu"},
            uploaded_by=test_user.id,
        )
        assert is_reference(ref)
        assert reference_display_label("prnu", "Sem rotulo") == "PRNU - Sem rotulo"

    def test_group_references(self, db_session, sample_case, test_user):
        refs = []
        for label in ("D70", "D70", "Cam2"):
            refs.append(
                Evidence(
                    id=uuid.uuid4(),
                    case_id=sample_case.id,
                    filename=f"{label}.jpg",
                    original_filename=f"{label}.jpg",
                    file_path="/x",
                    file_size=1,
                    file_type="imagem",
                    sha256=uuid.uuid4().hex,
                    extra_metadata={
                        "is_reference": True,
                        "reference_technique": "prnu",
                        "reference_group_label": label,
                    },
                    uploaded_by=test_user.id,
                )
            )
        groups = group_references(refs)
        assert len(groups) == 2
        labels = {g["group_label"] for g in groups}
        assert labels == {"Cam2", "D70"}


class TestReferenceUploadService:
    def test_prnu_reference_metadata(self, db_session, sample_case, test_user):
        from services.evidence_service import EvidenceService

        service = EvidenceService(db_session)
        ref = service.upload_evidence(
            case_id=sample_case.id,
            filename="ref.jpg",
            mime_type="image/jpeg",
            file_obj=io.BytesIO(_jpeg_bytes()),
            uploaded_by=test_user.id,
            extra_metadata={
                "is_reference": True,
                "reference_technique": "prnu",
                "reference_group_label": "D70",
                "prnu_reference": True,
            },
        )
        assert ref.extra_metadata["reference_group_label"] == "D70"
        assert is_reference(ref)
        assert not is_case_evidence(ref)

    def test_case_evidence_list_excludes_references(self, db_session, sample_case, test_user):
        from services.evidence_service import EvidenceService

        service = EvidenceService(db_session)
        service.upload_evidence(
            case_id=sample_case.id,
            filename="ev.jpg",
            mime_type="image/jpeg",
            file_obj=io.BytesIO(_jpeg_bytes()),
            uploaded_by=test_user.id,
        )
        service.upload_evidence(
            case_id=sample_case.id,
            filename="ref.jpg",
            mime_type="image/jpeg",
            file_obj=io.BytesIO(_jpeg_bytes()),
            uploaded_by=test_user.id,
            extra_metadata={
                "is_reference": True,
                "reference_technique": "prnu",
                "reference_group_label": "D70",
            },
        )
        all_rows = (
            db_session.query(Evidence)
            .filter(Evidence.case_id == sample_case.id, Evidence.deleted_at.is_(None))
            .all()
        )
        case_only = [e for e in all_rows if is_case_evidence(e)]
        refs_only = group_references(all_rows)
        assert len(case_only) == 1
        assert case_only[0].original_filename == "ev.jpg"
        assert len(refs_only) == 1
        assert refs_only[0]["display_label"] == "PRNU - D70"
        assert len(refs_only[0]["evidences"]) == 1
