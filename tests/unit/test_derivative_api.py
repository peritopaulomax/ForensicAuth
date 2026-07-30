"""HTTP endpoints de derivatives / lineage (API).

SPLIT mecânico (Fase 3g) a partir de test_derivative.py.
Checklist: todos os cases KEEP (ver PRUNE_PLAN Fase 3g).
"""

from __future__ import annotations

import uuid

import cv2
import numpy as np

from models.analysis_job import AnalysisJob

from derivative_support import build_job_result_dir, seed_job_preview

_seed_job_preview = seed_job_preview


class TestDerivativeEndpoint:
    def test_save_derivative_http(
        self, client, db_session, sample_case, test_user, sample_evidence, auth_headers
    ):
        from app.config import get_settings

        settings = get_settings()
        job_id = uuid.uuid4()
        result_dir = build_job_result_dir(settings.RESULTS_DIR, sample_case.id, sample_evidence.id, job_id)
        result_dir.mkdir(parents=True, exist_ok=True)
        ela_img = np.full((4, 4, 3), 40, dtype=np.uint8)
        cv2.imwrite(str(result_dir / "heatmap_base.png"), ela_img)
        cv2.imwrite(str(result_dir / "heatmap.png"), ela_img)
        params = {"quality": 90, "channel_mode": "y"}
        receipt = _seed_job_preview(
            job_id=job_id,
            result_dir=result_dir,
            technique="ela",
            parameters=params,
            evidence_sha256=sample_evidence.sha256,
        )

        job = AnalysisJob(
            id=job_id,
            evidence_id=sample_evidence.id,
            technique="ela",
            status="completed",
            parameters=params,
            result_path=str(result_dir),
            runtime_manifest=receipt,
            created_by=test_user.id,
        )
        db_session.add(job)
        db_session.commit()

        response = client.post(
            "/api/v1/evidences/derivatives",
            json={"job_id": str(job_id), "artifact_filename": "heatmap.png"},
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["evidence"]["extra_metadata"]["origin"] == "derived"
        assert "cadeia" in data["message"].lower()
        duplicate = client.post(
            "/api/v1/evidences/derivatives",
            json={"job_id": str(job_id), "artifact_filename": "heatmap.png"},
            headers=auth_headers,
        )
        assert duplicate.status_code == 200
        assert duplicate.json()["evidence"]["id"] == data["evidence"]["id"]
        assert "ja foi salvo" in duplicate.json()["message"].lower()

        audit = client.get(
            "/api/v1/audit",
            params={"case_id": str(sample_case.id)},
            headers=auth_headers,
        )
        types = [r["record_type"] for r in audit.json()]
        assert "derivative_saved" in types

    def test_list_derivatives_excludes_from_evidences(
        self, client, db_session, sample_case, test_user, sample_evidence, auth_headers
    ):
        from app.config import get_settings

        settings = get_settings()
        job_id = uuid.uuid4()
        result_dir = build_job_result_dir(settings.RESULTS_DIR, sample_case.id, sample_evidence.id, job_id)
        result_dir.mkdir(parents=True, exist_ok=True)
        ela_img = np.full((4, 4, 3), 40, dtype=np.uint8)
        cv2.imwrite(str(result_dir / "heatmap_base.png"), ela_img)
        cv2.imwrite(str(result_dir / "heatmap.png"), ela_img)
        params = {"quality": 90}
        receipt = _seed_job_preview(
            job_id=job_id,
            result_dir=result_dir,
            technique="ela",
            parameters=params,
            evidence_sha256=sample_evidence.sha256,
        )

        job = AnalysisJob(
            id=job_id,
            evidence_id=sample_evidence.id,
            technique="ela",
            status="completed",
            parameters=params,
            result_path=str(result_dir),
            runtime_manifest=receipt,
            created_by=test_user.id,
        )
        db_session.add(job)
        db_session.commit()

        client.post(
            "/api/v1/evidences/derivatives",
            json={"job_id": str(job_id), "artifact_filename": "heatmap.png"},
            headers=auth_headers,
        )

        evs = client.get(
            f"/api/v1/cases/{sample_case.id}/evidences",
            headers=auth_headers,
        )
        assert evs.status_code == 200
        assert len(evs.json()) == 1
        assert all(e["extra_metadata"].get("origin") != "derived" for e in evs.json())

        derivs = client.get(
            f"/api/v1/cases/{sample_case.id}/derivatives",
            headers=auth_headers,
        )
        assert derivs.status_code == 200
        assert len(derivs.json()) == 1
        assert derivs.json()[0]["extra_metadata"]["origin"] == "derived"
        assert derivs.json()[0]["extra_metadata"]["procedure_summary"]

    def test_lineage_chain(
        self, client, db_session, sample_case, test_user, sample_evidence, auth_headers
    ):
        from app.config import get_settings
        from services.derivative_service import DerivativeService

        settings = get_settings()
        service = DerivativeService(db_session)

        job1_id = uuid.uuid4()
        result1 = build_job_result_dir(settings.RESULTS_DIR, sample_case.id, sample_evidence.id, job1_id)
        result1.mkdir(parents=True, exist_ok=True)
        ela1 = np.full((4, 4, 3), 40, dtype=np.uint8)
        cv2.imwrite(str(result1 / "heatmap_base.png"), ela1)
        cv2.imwrite(str(result1 / "heatmap.png"), ela1)
        params1 = {"quality": 90, "channel_mode": "rgb"}
        receipt1 = _seed_job_preview(
            job_id=job1_id,
            result_dir=result1,
            technique="ela",
            parameters=params1,
            evidence_sha256=sample_evidence.sha256,
        )
        job1 = AnalysisJob(
            id=job1_id,
            evidence_id=sample_evidence.id,
            technique="ela",
            status="completed",
            parameters=params1,
            result_path=str(result1),
            runtime_manifest=receipt1,
            created_by=test_user.id,
        )
        db_session.add(job1)
        db_session.commit()

        d1 = service.save_from_job(job1_id, "heatmap.png", test_user.id)

        job2_id = uuid.uuid4()
        result2 = build_job_result_dir(settings.RESULTS_DIR, sample_case.id, d1.id, job2_id)
        result2.mkdir(parents=True, exist_ok=True)
        ela2 = np.full((4, 4, 3), 55, dtype=np.uint8)
        cv2.imwrite(str(result2 / "heatmap_base.png"), ela2)
        cv2.imwrite(str(result2 / "heatmap.png"), ela2)
        params2 = {"quality": 85, "channel_mode": "y"}
        receipt2 = _seed_job_preview(
            job_id=job2_id,
            result_dir=result2,
            technique="ela",
            parameters=params2,
            evidence_sha256=d1.sha256,
        )
        job2 = AnalysisJob(
            id=job2_id,
            evidence_id=d1.id,
            technique="ela",
            status="completed",
            parameters=params2,
            result_path=str(result2),
            runtime_manifest=receipt2,
            created_by=test_user.id,
        )
        db_session.add(job2)
        db_session.commit()

        d2 = service.save_from_job(job2_id, "heatmap.png", test_user.id)

        response = client.get(
            f"/api/v1/evidences/{d2.id}/lineage",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["nodes"]) == 3
        by_layer = sorted(data["nodes"], key=lambda n: n.get("layer", 0))
        assert by_layer[0]["is_derived"] is False
        assert all(n["is_derived"] for n in by_layer[1:])
        assert len(data["edges"]) == 2
        assert data["edges"][0]["technique"] == "ela"
        assert data["target_id"] == str(d2.id)
