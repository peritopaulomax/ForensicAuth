"""Tests for DCT reference-mode job submission parameter resolution."""

import uuid

from models.evidence import Evidence
from services.job_service import JobService


def test_submit_dct_reference_accepts_reference_evidence_id(
    db_session, sample_case, sample_evidence, test_user
):
    reference = Evidence(
        id=uuid.uuid4(),
        case_id=sample_case.id,
        filename="ref.jpg",
        original_filename="ref.jpg",
        file_path="/uploads/ref.jpg",
        file_size=2048,
        file_type="imagem",
        mime_type="image/jpeg",
        sha256="b" * 64,
        extra_metadata={"reference": True, "for_technique": "dct_quantization"},
        uploaded_by=test_user.id,
    )
    db_session.add(reference)
    db_session.commit()
    db_session.refresh(reference)

    service = JobService(db_session)
    job = service.submit_job(
        evidence_id=sample_evidence.id,
        technique="dct_quantization",
        parameters={"mode": "reference", "reference_evidence_id": str(reference.id)},
        user_id=test_user.id,
    )

    assert job.parameters["mode"] == "reference"
    assert job.parameters["reference_evidence_id"] == str(reference.id)
    assert job.parameters["reference_path"] == reference.file_path
