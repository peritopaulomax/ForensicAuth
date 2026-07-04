"""Integracao API: DistilDIRE removido das tecnicas ativas."""

from __future__ import annotations

import uuid

import pytest
from PIL import Image


@pytest.mark.integration
class TestDistilDireApiIntegration:
    def test_techniques_does_not_list_distildire(self, client, auth_headers):
        res = client.get("/api/v1/analysis/techniques", headers=auth_headers)
        assert res.status_code == 200
        names = {t["name"] for t in res.json()}
        assert "distildire" not in names

    def test_post_analysis_job_distildire_is_rejected(
        self, client, auth_headers, db_session, sample_case, test_user, tmp_path
    ):
        from models.evidence import Evidence

        img_path = tmp_path / "evidence.jpg"
        Image.new("RGB", (256, 256), (120, 80, 40)).save(img_path)

        evidence = Evidence(
            id=uuid.uuid4(),
            case_id=sample_case.id,
            filename="evidence.jpg",
            original_filename="evidence.jpg",
            file_path=str(img_path),
            file_size=img_path.stat().st_size,
            file_type="imagem",
            mime_type="image/jpeg",
            sha256="b" * 64,
            uploaded_by=test_user.id,
        )
        db_session.add(evidence)
        db_session.commit()

        create = client.post(
            "/api/v1/analysis",
            headers=auth_headers,
            json={
                "evidence_id": str(evidence.id),
                "technique": "distildire",
                "parameters": {"checkpoint": "imagenet", "threshold": 0.5},
            },
        )
        assert create.status_code == 422, create.text
        assert "distildire" in create.text
