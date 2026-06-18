"""Integracao API: job DistilDIRE via HTTP (frontend → backend)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from PIL import Image


@pytest.mark.integration
class TestDistilDireApiIntegration:
    def test_techniques_lists_distildire(self, client, auth_headers):
        res = client.get("/api/v1/analysis/techniques", headers=auth_headers)
        assert res.status_code == 200
        names = {t["name"] for t in res.json()}
        assert "distildire" in names

    def test_post_analysis_job_distildire_mocked(
        self, client, auth_headers, db_session, sample_case, test_user, tmp_path, monkeypatch
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

        from core.legacy.distildire.distildire_pipeline import DistilDireAnalysis

        preview = Image.open(img_path).convert("RGB")

        def fake_run(*_a, **_k):
            return DistilDireAnalysis(
                df_probability=0.77,
                prediction="FAKE",
                threshold=0.5,
                checkpoint="imagenet",
                input_image=preview,
                eps_heatmap=preview,
                inference_device="CPU",
            )

        monkeypatch.setattr("api.v1.endpoints.analysis.run_job_in_background", lambda _job_id: None)
        monkeypatch.setattr(
            "core.legacy.distildire.distildire_pipeline.run_distildire_analysis",
            fake_run,
        )

        create = client.post(
            "/api/v1/analysis",
            headers=auth_headers,
            json={
                "evidence_id": str(evidence.id),
                "technique": "distildire",
                "parameters": {"checkpoint": "imagenet", "threshold": 0.5},
            },
        )
        assert create.status_code == 201, create.text
        job_id = create.json()["job_id"]

        from services.job_service import JobService

        JobService(db_session).run_job(uuid.UUID(job_id))
        db_session.expire_all()

        detail = client.get(f"/api/v1/analysis/{job_id}", headers=auth_headers)
        assert detail.status_code == 200
        assert detail.json()["status"] == "completed"

        result = client.get(f"/api/v1/analysis/{job_id}/result", headers=auth_headers)
        assert result.status_code == 200
        body = result.json()
        assert body.get("success") is True
        assert body.get("prediction") == "FAKE"
        assert isinstance(body.get("df_probability"), float)

        report_file = client.get(
            f"/api/v1/analysis/{job_id}/result/file?filename=distildire_report.json",
            headers=auth_headers,
        )
        assert report_file.status_code == 200
        report = json.loads(report_file.content)
        assert report["technique"] == "distildire"
        assert report["prediction"] == "FAKE"
