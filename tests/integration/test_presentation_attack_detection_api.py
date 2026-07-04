"""Integracao API: job PAD via HTTP (frontend → backend)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from PIL import Image


@pytest.mark.integration
class TestPresentationAttackDetectionApiIntegration:
    def test_techniques_lists_pad(self, client, auth_headers):
        res = client.get("/api/v1/analysis/techniques", headers=auth_headers)
        assert res.status_code == 200
        names = {t["name"] for t in res.json()}
        assert "presentation_attack_detection" in names

    def test_post_analysis_job_pad_mocked(
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
            sha256="b" * 64,
            uploaded_by=test_user.id,
        )
        db_session.add(evidence)
        db_session.commit()

        monkeypatch.setattr("api.v1.endpoints.analysis.run_job_in_background", lambda _job_id: None)
        # Stub the plugin execution path directly so the test does not depend on
        # the vendored face detector or model weights.
        monkeypatch.setattr(
            "services.job_service.JobService._execute_plugin_analysis",
            lambda _self, _job, _evidence, progress_reporter=None, staging_dir=None: {
                "success": True,
                "adapter": "presentation_attack_detection",
                "status": "completed",
                "label": "fake",
                "raw_label": "fake",
                "score": 0.23,
                "threshold": 0.5,
                "bbox": {"x": 10, "y": 10, "w": 100, "h": 100},
                "inference_device": "CPU",
                "models_used": ["2.7_80x80_MiniFASNetV2.pth"],
                "pad_result_json_path": str(staging_dir / "pad_result.json") if staging_dir else None,
                "pad_annotated_image_path": str(staging_dir / "pad_annotated.png") if staging_dir else None,
                "pad_face_crop_path": str(staging_dir / "pad_face_crop.png") if staging_dir else None,
            },
        )

        create = client.post(
            "/api/v1/analysis",
            headers=auth_headers,
            json={
                "evidence_id": str(evidence.id),
                "technique": "presentation_attack_detection",
                "parameters": {"threshold": 0.5},
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
        assert body.get("label") == "fake"
        assert isinstance(body.get("score"), float)

    def test_post_analysis_job_pad_no_face(
        self, client, auth_headers, db_session, sample_case, test_user, tmp_path, monkeypatch
    ):
        from models.evidence import Evidence

        img_path = tmp_path / "noface.jpg"
        Image.new("RGB", (480, 360), (128, 128, 128)).save(img_path)

        evidence = Evidence(
            id=uuid.uuid4(),
            case_id=sample_case.id,
            filename="noface.jpg",
            original_filename="noface.jpg",
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

        create = client.post(
            "/api/v1/analysis",
            headers=auth_headers,
            json={
                "evidence_id": str(evidence.id),
                "technique": "presentation_attack_detection",
                "parameters": {},
            },
        )
        assert create.status_code == 201, create.text
        job_id = create.json()["job_id"]

        from services.job_service import JobService

        JobService(db_session).run_job(uuid.UUID(job_id))
        db_session.expire_all()

        detail = client.get(f"/api/v1/analysis/{job_id}", headers=auth_headers)
        assert detail.status_code == 200
        assert detail.json()["status"] == "failed"
        assert "NO_FACE_DETECTED" in detail.json().get("error_message", "")

    def test_pad_smoke_with_real_weights(
        self, client, auth_headers, db_session, sample_case, test_user, tmp_path, monkeypatch
    ):
        import urllib.request

        from core.legacy.pad.runtime import pad_runtime_status
        from models.evidence import Evidence

        monkeypatch.setattr("api.v1.endpoints.analysis.run_job_in_background", lambda _job_id: None)

        ok, reason = pad_runtime_status()
        if not ok:
            pytest.skip(reason or "Pesos PAD ausentes")

        sample_url = "https://raw.githubusercontent.com/minivision-ai/Silent-Face-Anti-Spoofing/master/images/sample/image_F1.jpg"
        img_path = tmp_path / "face.jpg"
        try:
            urllib.request.urlretrieve(sample_url, img_path)
        except Exception as exc:
            pytest.skip(f"Nao foi possivel baixar imagem de exemplo: {exc}")

        evidence = Evidence(
            id=uuid.uuid4(),
            case_id=sample_case.id,
            filename="face.jpg",
            original_filename="face.jpg",
            file_path=str(img_path),
            file_size=img_path.stat().st_size,
            file_type="imagem",
            mime_type="image/jpeg",
            sha256="d" * 64,
            uploaded_by=test_user.id,
        )
        db_session.add(evidence)
        db_session.commit()

        create = client.post(
            "/api/v1/analysis",
            headers=auth_headers,
            json={
                "evidence_id": str(evidence.id),
                "technique": "presentation_attack_detection",
                "parameters": {"threshold": 0.5},
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
        assert body.get("adapter") == "presentation_attack_detection"
        assert body.get("label") in ("real", "fake")
        assert isinstance(body.get("score"), float)
        assert isinstance(body.get("bbox"), dict)
