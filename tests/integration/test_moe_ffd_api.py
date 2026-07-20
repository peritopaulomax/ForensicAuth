"""Integracao API: job MoE-FFD via HTTP (frontend → backend)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from PIL import Image


@pytest.mark.integration
class TestMoeFfdApiIntegration:
    def test_techniques_lists_moe_ffd(self, client, auth_headers):
        res = client.get("/api/v1/analysis/techniques", headers=auth_headers)
        assert res.status_code == 200
        names = {t["name"] for t in res.json()}
        assert "moe_ffd" in names

    def test_post_analysis_job_moe_ffd_mocked(
        self, client, auth_headers, db_session, sample_case, test_user, tmp_path, monkeypatch
    ):
        from models.evidence import Evidence

        img_path = tmp_path / "evidence.jpg"
        Image.new("RGB", (320, 240), (120, 80, 40)).save(img_path)

        evidence = Evidence(
            id=uuid.uuid4(),
            case_id=sample_case.id,
            filename="evidence.jpg",
            original_filename="evidence.jpg",
            file_path=str(img_path),
            file_size=img_path.stat().st_size,
            file_type="imagem",
            mime_type="image/jpeg",
            sha256="c" * 64,
            uploaded_by=test_user.id,
        )
        db_session.add(evidence)
        db_session.commit()

        monkeypatch.setattr("api.v1.endpoints.analysis.run_job_in_background", lambda _job_id: None)
        monkeypatch.setattr(
            "core.plugins.moe_ffd_adapter.moe_ffd_runtime_status",
            lambda: (True, ""),
        )
        monkeypatch.setattr(
            "core.legacy.moe_ffd.runtime.moe_ffd_runtime_status",
            lambda: (True, ""),
        )
        monkeypatch.setattr(
            "services.job_service.JobService._execute_plugin_analysis",
            lambda _self, _job, _evidence, progress_reporter=None, staging_dir=None: {
                "success": True,
                "adapter": "moe_ffd",
                "status": "completed",
                "label": "fake",
                "fake_prob": 0.88,
                "real_prob": 0.12,
                "score": 0.88,
                "threshold": 0.5,
                "inference_device": "cpu",
                "model_checkpoint": "MoE-FFD.tar",
                "moe_ffd_result_json_path": str(staging_dir / "moe_ffd_result.json") if staging_dir else None,
                "moe_ffd_summary_txt_path": str(staging_dir / "moe_ffd_summary.txt") if staging_dir else None,
                "input_image_path": str(staging_dir / "moe_ffd_input.png") if staging_dir else None,
            },
        )

        create = client.post(
            "/api/v1/analysis",
            headers=auth_headers,
            json={
                "evidence_id": str(evidence.id),
                "technique": "moe_ffd",
                "parameters": {"threshold": 0.5},
            },
        )
        assert create.status_code == 201, create.text
        job_id = create.json()["job_id"]

        from services.job_service import JobService

        JobService(db_session).run_job(uuid.UUID(job_id))
        db_session.expire_all()

        status = client.get(f"/api/v1/analysis/{job_id}", headers=auth_headers)
        assert status.status_code == 200
        assert status.json()["status"] == "completed"

        result = client.get(f"/api/v1/analysis/{job_id}/result", headers=auth_headers)
        assert result.status_code == 200
        body = result.json()
        assert body.get("success") is True
        assert body.get("adapter") == "moe_ffd"
        assert body.get("label") == "fake"
        assert isinstance(body.get("score"), float)
