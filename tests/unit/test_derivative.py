"""Tests for saving analysis results as derived evidence."""

import json
import uuid
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pytest

from models.analysis_job import AnalysisJob
from models.custody_record import CustodyRecord
from models.evidence import Evidence


def _seed_job_preview(
    *,
    job_id: uuid.UUID,
    result_dir: Path,
    technique: str,
    parameters: dict[str, Any],
    extra_result: dict[str, Any] | None = None,
    evidence_sha256: str | None = None,
) -> dict[str, Any]:
    """Write result.json with job_execution_receipt (preview-tier promote flow)."""
    from app.config import get_settings
    from core.reproducibility import build_job_execution_receipt, build_runtime_manifest

    settings = get_settings()
    result: dict[str, Any] = {
        "success": True,
        "adapter": technique,
        "status": "completed",
        "preview": True,
        "promoted": False,
        **(extra_result or {}),
    }
    runtime = build_runtime_manifest(
        app_version=settings.APP_VERSION,
        gpu_available=settings.GPU_AVAILABLE,
        models_dir=settings.MODELS_DIR,
        technique=technique,
    )
    receipt = build_job_execution_receipt(
        technique=technique,
        result=result,
        runtime_manifest=runtime,
        job_id=str(job_id),
        parameters=parameters,
        input_evidence_sha256=evidence_sha256,
    )
    result["job_receipt"] = receipt
    (result_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return receipt


class TestDerivativeService:
    def test_save_derivative_from_completed_job(
        self, db_session, sample_case, test_user, sample_evidence, tmp_path, monkeypatch
    ):
        from app.config import get_settings
        from services.derivative_service import DerivativeService

        settings = get_settings()
        job_id = uuid.uuid4()
        result_dir = Path(settings.RESULTS_DIR) / str(job_id)
        result_dir.mkdir(parents=True, exist_ok=True)
        base = np.full((8, 8, 3), 40, dtype=np.uint8)
        cv2.imwrite(str(result_dir / "heatmap_base.png"), base)
        artifact = result_dir / "heatmap.png"
        cv2.imwrite(str(artifact), base)
        params = {"quality": 95, "channel_mode": "rgb", "gain": 1.0}
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

        service = DerivativeService(db_session)
        derivative = service.save_from_job(
            job_id=job_id,
            artifact_filename="heatmap.png",
            user_id=test_user.id,
        )

        assert derivative.case_id == sample_case.id
        assert derivative.sha256
        assert derivative.extra_metadata["origin"] == "derived"
        assert derivative.extra_metadata["parent_evidence_id"] == str(sample_evidence.id)
        assert derivative.extra_metadata["source_job_id"] == str(job_id)
        assert derivative.extra_metadata.get("provenance_schema_version") == "1"
        assert Path(derivative.file_path).exists()

        parent_inputs = derivative.extra_metadata["parent_inputs"]
        assert len(parent_inputs) == 1
        assert parent_inputs[0]["sha256"] == sample_evidence.sha256
        assert parent_inputs[0]["original_filename"] == sample_evidence.original_filename

        custody = (
            db_session.query(CustodyRecord)
            .filter(CustodyRecord.record_type == "derivative_saved")
            .one()
        )
        assert custody.sha256_input == sample_evidence.sha256
        assert custody.sha256_output == derivative.sha256
        assert custody.job_id == job_id
        assert custody.details.get("provenance_schema_version") == "1"
        assert custody.details["parent_inputs"][0]["sha256"] == sample_evidence.sha256
        assert custody.details["operation"]["technique"] == "ela"

    def test_save_imdl_mask_uses_effective_threshold(
        self, db_session, sample_case, test_user, sample_evidence
    ):
        from app.config import get_settings
        from services.derivative_service import DerivativeService

        settings = get_settings()
        job_id = uuid.uuid4()
        result_dir = Path(settings.RESULTS_DIR) / str(job_id)
        result_dir.mkdir(parents=True, exist_ok=True)
        scores = np.array([[30, 200]], dtype=np.uint8)
        cv2.imwrite(str(result_dir / "score_map.png"), scores)
        cv2.imwrite(str(result_dir / "mask.png"), np.zeros_like(scores))
        params = {"method": "trufor", "threshold": 0.5}
        receipt = _seed_job_preview(
            job_id=job_id,
            result_dir=result_dir,
            technique="imdlbenco",
            parameters=params,
            evidence_sha256=sample_evidence.sha256,
        )
        job = AnalysisJob(
            id=job_id,
            evidence_id=sample_evidence.id,
            technique="imdlbenco",
            status="completed",
            parameters=params,
            result_path=str(result_dir),
            runtime_manifest=receipt,
            created_by=test_user.id,
        )
        db_session.add(job)
        db_session.commit()

        DerivativeService(db_session).save_from_job(
            job_id=job_id,
            artifact_filename="mask.png",
            user_id=test_user.id,
            effective_parameters={"method": "trufor", "threshold": 0.7},
        )

        db_session.refresh(job)
        assert job.parameters["threshold"] == 0.7
        mask = cv2.imread(str(result_dir / "mask.png"), cv2.IMREAD_GRAYSCALE)
        assert int(mask[0, 0]) == 0
        assert int(mask[0, 1]) == 255

    def test_save_ela_derivative_applies_effective_gain(
        self, db_session, sample_case, test_user, sample_evidence
    ):
        from app.config import get_settings
        from services.derivative_service import DerivativeService

        settings = get_settings()
        job_id = uuid.uuid4()
        result_dir = Path(settings.RESULTS_DIR) / str(job_id)
        result_dir.mkdir(parents=True, exist_ok=True)
        base = np.full((8, 8, 3), 50, dtype=np.uint8)
        cv2.imwrite(str(result_dir / "heatmap_base.png"), base)
        cv2.imwrite(str(result_dir / "heatmap.png"), base)
        params = {"quality": 90, "channel_mode": "rgb", "gain": 1.0}
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

        derivative = DerivativeService(db_session).save_from_job(
            job_id=job_id,
            artifact_filename="heatmap.png",
            user_id=test_user.id,
            effective_parameters={"gain": 2.0, "quality": 90, "channel_mode": "rgb"},
        )

        db_session.refresh(job)
        assert job.parameters["gain"] == 2.0
        prov_params = derivative.extra_metadata["provenance"]["operation"]["parameters"]
        assert prov_params["gain"] == 2.0
        result_payload = json.loads((result_dir / "result.json").read_text(encoding="utf-8"))
        assert result_payload["effective_parameters"]["gain"] == 2.0

    def test_save_wavelet_derivative_materializes_threshold(
        self, db_session, sample_case, test_user, sample_evidence
    ):
        from app.config import get_settings
        from core.legacy.wavelet_noise_residue import run_wavelet_noise_residue
        from services.derivative_service import DerivativeService

        settings = get_settings()
        job_id = uuid.uuid4()
        result_dir = Path(settings.RESULTS_DIR) / str(job_id)
        result_dir.mkdir(parents=True, exist_ok=True)
        gray = np.random.default_rng(9).integers(30, 200, (64, 64), dtype=np.uint8)
        npz_path = result_dir / "wnr_dwt_coefficients.npz"
        run_wavelet_noise_residue(gray, {"order": 8, "blocksize": 3, "thr": 255}, dwt_coefficients_path=npz_path)
        stale = np.zeros((64, 64, 3), dtype=np.uint8)
        cv2.imwrite(str(result_dir / "overlay.png"), stale)
        params = {"levels_slider": 4, "order": 8, "blocksize": 3, "thr": 255, "post": True}
        receipt = _seed_job_preview(
            job_id=job_id,
            result_dir=result_dir,
            technique="wavelet_noise_residue",
            parameters=params,
            evidence_sha256=sample_evidence.sha256,
        )
        job = AnalysisJob(
            id=job_id,
            evidence_id=sample_evidence.id,
            technique="wavelet_noise_residue",
            status="completed",
            parameters=params,
            result_path=str(result_dir),
            runtime_manifest=receipt,
            created_by=test_user.id,
        )
        db_session.add(job)
        db_session.commit()

        derivative = DerivativeService(db_session).save_from_job(
            job_id=job_id,
            artifact_filename="overlay.png",
            user_id=test_user.id,
            effective_parameters={"blocksize": 3, "thr": 64, "post": True, "order": 8},
        )

        overlay = cv2.imread(str(result_dir / "overlay.png"))
        assert overlay is not None
        assert int(np.max(overlay)) > 0
        assert derivative.extra_metadata["provenance"]["operation"]["parameters"]["thr"] == 64
        result_payload = json.loads((result_dir / "result.json").read_text(encoding="utf-8"))
        assert result_payload["promoted_derivatives"][0]["artifact_filename"] == "overlay.png"
        db_session.refresh(job)
        assert job.runtime_manifest["parameters"]["thr"] == 64

    def test_save_prnu_localized_derivative_lists_fingerprint_parent(
        self, db_session, sample_case, test_user, sample_evidence
    ):
        from app.config import get_settings
        from services.derivative_service import DerivativeService

        settings = get_settings()
        fp_id = uuid.uuid4()
        fp_evidence = Evidence(
            id=fp_id,
            case_id=sample_case.id,
            filename=f"{fp_id}.npy",
            original_filename="fingerprint.npy",
            file_path="/tmp/fp.npy",
            file_size=128,
            file_type="imagem",
            mime_type="application/octet-stream",
            sha256="f" * 64,
            uploaded_by=test_user.id,
        )
        db_session.add(fp_evidence)

        job_id = uuid.uuid4()
        result_dir = Path(settings.RESULTS_DIR) / str(job_id)
        result_dir.mkdir(parents=True, exist_ok=True)
        artifact = result_dir / "localized_map.png"
        cv2.imwrite(str(artifact), np.zeros((8, 8), dtype=np.uint8))
        params = {
            "fingerprint_id": str(fp_id),
            "block_half": 16,
            "overlap_k": 40,
            "localized_threshold": 0.2,
        }
        receipt = _seed_job_preview(
            job_id=job_id,
            result_dir=result_dir,
            technique="prnu",
            parameters=params,
            evidence_sha256=sample_evidence.sha256,
        )
        job = AnalysisJob(
            id=job_id,
            evidence_id=sample_evidence.id,
            technique="prnu",
            status="completed",
            parameters=params,
            result_path=str(result_dir),
            runtime_manifest=receipt,
            created_by=test_user.id,
        )
        db_session.add(job)
        db_session.commit()

        derivative = DerivativeService(db_session).save_from_job(
            job_id=job_id,
            artifact_filename="localized_map.png",
            user_id=test_user.id,
            effective_parameters=params,
        )
        parents = derivative.extra_metadata["provenance"]["parent_inputs"]
        roles = {p["role"] for p in parents}
        assert "questioned" in roles
        assert "fingerprint" in roles
        assert derivative.extra_metadata["provenance"]["output"]["artifact_role"] == "prnu_localized_map"

    def test_save_imdlbenco_trufor_derivative_uses_method_identifier(
        self, db_session, sample_case, test_user, sample_evidence
    ):
        from app.config import get_settings
        from services.derivative_service import DerivativeService

        settings = get_settings()
        job_id = uuid.uuid4()
        result_dir = Path(settings.RESULTS_DIR) / str(job_id)
        result_dir.mkdir(parents=True, exist_ok=True)
        artifact = result_dir / "heatmap.png"
        artifact.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
        params = {"method": "trufor", "threshold": 0.5}
        receipt = _seed_job_preview(
            job_id=job_id,
            result_dir=result_dir,
            technique="imdlbenco",
            parameters=params,
            extra_result={"method": "trufor"},
            evidence_sha256=sample_evidence.sha256,
        )

        job = AnalysisJob(
            id=job_id,
            evidence_id=sample_evidence.id,
            technique="imdlbenco",
            status="completed",
            parameters=params,
            result_path=str(result_dir),
            runtime_manifest=receipt,
            created_by=test_user.id,
        )
        db_session.add(job)
        db_session.commit()

        derivative = DerivativeService(db_session).save_from_job(
            job_id=job_id,
            artifact_filename="heatmap.png",
            user_id=test_user.id,
        )

        assert derivative.extra_metadata["technique"] == "trufor"
        assert derivative.extra_metadata["derivation_step"] == "trufor_heatmap_save"
        assert derivative.extra_metadata["artifact_role"] == "trufor_heatmap"
        custody = (
            db_session.query(CustodyRecord)
            .filter(CustodyRecord.record_type == "derivative_saved")
            .one()
        )
        assert custody.details["operation"]["technique"] == "trufor"
        assert custody.details["operation"]["derivation_step"] == "trufor_heatmap_save"

    def test_save_safire_derivative_uses_technique_specific_step(
        self, db_session, sample_case, test_user, sample_evidence
    ):
        from app.config import get_settings
        from services.derivative_service import DerivativeService

        settings = get_settings()
        job_id = uuid.uuid4()
        result_dir = Path(settings.RESULTS_DIR) / str(job_id)
        result_dir.mkdir(parents=True, exist_ok=True)
        (result_dir / "overlay.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
        params = {"mode": "binary"}
        receipt = _seed_job_preview(
            job_id=job_id,
            result_dir=result_dir,
            technique="safire",
            parameters=params,
            evidence_sha256=sample_evidence.sha256,
        )

        job = AnalysisJob(
            id=job_id,
            evidence_id=sample_evidence.id,
            technique="safire",
            status="completed",
            parameters=params,
            result_path=str(result_dir),
            runtime_manifest=receipt,
            created_by=test_user.id,
        )
        db_session.add(job)
        db_session.commit()

        derivative = DerivativeService(db_session).save_from_job(
            job_id=job_id,
            artifact_filename="overlay.png",
            user_id=test_user.id,
        )

        assert derivative.extra_metadata["derivation_step"] == "safire_overlay_save"
        assert derivative.extra_metadata["artifact_role"] == "safire_overlay"

    def test_save_derivative_jpg_from_pdf_parent_sets_image_metadata(
        self, db_session, sample_case, test_user, tmp_path, monkeypatch
    ):
        from app.config import get_settings
        from services.derivative_service import DerivativeService

        settings = get_settings()
        pdf_parent = Evidence(
            id=uuid.uuid4(),
            case_id=sample_case.id,
            filename="doc.pdf",
            original_filename="documento.pdf",
            file_path=str(tmp_path / "doc.pdf"),
            file_size=128,
            file_type="pdf",
            mime_type="application/pdf",
            sha256="a" * 64,
            uploaded_by=test_user.id,
        )
        db_session.add(pdf_parent)
        db_session.commit()

        job_id = uuid.uuid4()
        result_dir = Path(settings.RESULTS_DIR) / str(job_id)
        result_dir.mkdir(parents=True, exist_ok=True)
        artifact = result_dir / "images" / "image_00001.jpg"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 32)
        _seed_job_preview(
            job_id=job_id,
            result_dir=result_dir,
            technique="pdf_forensic_extract",
            parameters={},
            evidence_sha256=pdf_parent.sha256,
        )
        job = AnalysisJob(
            id=job_id,
            evidence_id=pdf_parent.id,
            technique="pdf_forensic_extract",
            status="completed",
            parameters={},
            result_path=str(result_dir),
            created_by=test_user.id,
        )
        db_session.add(job)
        db_session.commit()

        derivative = DerivativeService(db_session).save_from_job(
            job_id=job_id,
            artifact_filename="images/image_00001.jpg",
            user_id=test_user.id,
            label="pdf_extract_image",
        )
        assert derivative.file_type == "imagem"
        assert derivative.mime_type == "image/jpeg"
        assert derivative.filename.endswith(".jpg")

    def test_save_derivative_rejects_incomplete_job(
        self, db_session, test_user, sample_evidence
    ):
        from services.derivative_service import DerivativeService

        job = AnalysisJob(
            id=uuid.uuid4(),
            evidence_id=sample_evidence.id,
            technique="ela",
            status="pending",
            parameters={},
            created_by=test_user.id,
        )
        db_session.add(job)
        db_session.commit()

        service = DerivativeService(db_session)
        with pytest.raises(Exception) as exc:
            service.save_from_job(job.id, "heatmap.png", test_user.id)
        assert exc.value.status_code == 409

    def test_save_similarity_matrix_derivative_registers_all_inputs(
        self, db_session, sample_case, test_user, sample_evidence, tmp_path
    ):
        from app.config import get_settings
        from services.derivative_service import DerivativeService

        settings = get_settings()
        extra_videos = []
        for idx, name in enumerate(("video_b.mp4", "video_c.mp4"), start=1):
            ev = Evidence(
                id=uuid.uuid4(),
                case_id=sample_case.id,
                filename=f"extra{idx}.mp4",
                original_filename=name,
                file_path=str(tmp_path / name),
                file_size=128,
                file_type="video",
                mime_type="video/mp4",
                sha256=f"{'a' * 63}{idx}",
                uploaded_by=test_user.id,
            )
            db_session.add(ev)
            extra_videos.append(ev)
        db_session.commit()

        all_ids = [sample_evidence.id, extra_videos[0].id, extra_videos[1].id]
        job_id = uuid.uuid4()
        result_dir = Path(settings.RESULTS_DIR) / str(job_id)
        result_dir.mkdir(parents=True, exist_ok=True)
        artifact = result_dir / "similarity_wl_kernel.png"
        artifact.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
        params = {
            "mode": "all_pairs",
            "questioned_evidence_ids": [str(i) for i in all_ids],
            "reference_evidence_ids": [],
        }
        receipt = _seed_job_preview(
            job_id=job_id,
            result_dir=result_dir,
            technique="isomedia_compare",
            parameters=params,
            extra_result={
                "questioned_count": 3,
                "reference_count": 0,
                "mode": "all_pairs",
            },
            evidence_sha256=sample_evidence.sha256,
        )

        job = AnalysisJob(
            id=job_id,
            evidence_id=sample_evidence.id,
            technique="isomedia_compare",
            status="completed",
            parameters=params,
            result_path=str(result_dir),
            runtime_manifest=receipt,
            created_by=test_user.id,
        )
        db_session.add(job)
        db_session.commit()

        derivative = DerivativeService(db_session).save_from_job(
            job_id=job_id,
            artifact_filename="similarity_wl_kernel.png",
            user_id=test_user.id,
            label="isomedia_compare_wl",
        )

        parent_inputs = derivative.extra_metadata["parent_inputs"]
        assert len(parent_inputs) == 3
        parent_ids = {p["evidence_id"] for p in parent_inputs}
        assert parent_ids == {str(i) for i in all_ids}
        assert "Matriz similaridade ISO BMFF (3×3)" in derivative.extra_metadata["procedure_summary"]
        assert derivative.extra_metadata["derivation_outputs"]["input_count"] == 3

        graph = DerivativeService(db_session).get_lineage(derivative.id)
        assert graph["parent_count"] == 3
        assert len(graph["operations"]) == 1
        assert graph["operations"][0]["input_count"] == 3

    def test_save_jpeg_structure_matrix_derivative_registers_all_inputs(
        self, db_session, sample_case, test_user, sample_evidence, tmp_path
    ):
        from app.config import get_settings
        from services.derivative_service import DerivativeService

        settings = get_settings()
        extra = Evidence(
            id=uuid.uuid4(),
            case_id=sample_case.id,
            filename="q2.jpg",
            original_filename="q2.jpg",
            file_path=str(tmp_path / "q2.jpg"),
            file_size=128,
            file_type="imagem",
            mime_type="image/jpeg",
            sha256="c" * 64,
            uploaded_by=test_user.id,
        )
        ref_ev = Evidence(
            id=uuid.uuid4(),
            case_id=sample_case.id,
            filename="ref.jpg",
            original_filename="ref.jpg",
            file_path=str(tmp_path / "ref.jpg"),
            file_size=128,
            file_type="imagem",
            mime_type="image/jpeg",
            sha256="d" * 64,
            uploaded_by=test_user.id,
            extra_metadata={"is_reference": True},
        )
        db_session.add(extra)
        db_session.add(ref_ev)
        db_session.commit()

        q_ids = [sample_evidence.id, extra.id]
        r_ids = [ref_ev.id]
        job_id = uuid.uuid4()
        result_dir = Path(settings.RESULTS_DIR) / str(job_id)
        result_dir.mkdir(parents=True, exist_ok=True)
        params = {
            "mode": "with_reference",
            "questioned_evidence_ids": [str(i) for i in q_ids],
            "reference_evidence_ids": [str(i) for i in r_ids],
        }
        receipt = _seed_job_preview(
            job_id=job_id,
            result_dir=result_dir,
            technique="jpeg_structure_compare",
            parameters=params,
            extra_result={
                "mode": "with_reference",
                "reference_count": 1,
                "questioned_count": 2,
                "criteria_version": "2026-06",
            },
            evidence_sha256=sample_evidence.sha256,
        )
        (result_dir / "jpeg_structure_matrix.json").write_text(
            '{"mode":"with_reference","reference_count":1,"questioned_count":2,"criteria_version":"2026-06"}',
            encoding="utf-8",
        )

        job = AnalysisJob(
            id=job_id,
            evidence_id=sample_evidence.id,
            technique="jpeg_structure_compare",
            status="completed",
            parameters=params,
            result_path=str(result_dir),
            runtime_manifest=receipt,
            created_by=test_user.id,
        )
        db_session.add(job)
        db_session.commit()

        derivative = DerivativeService(db_session).save_from_job(
            job_id=job_id,
            artifact_filename="jpeg_structure_matrix.json",
            user_id=test_user.id,
            label="jpeg_estrutura_test",
        )

        parent_inputs = derivative.extra_metadata["parent_inputs"]
        assert len(parent_inputs) == 3
        parent_ids = {p["evidence_id"] for p in parent_inputs}
        assert parent_ids == {str(i) for i in [*r_ids, *q_ids]}
        assert "JPEG estrutural" in derivative.extra_metadata["procedure_summary"] or "Matriz" in derivative.extra_metadata["procedure_summary"]
        assert derivative.file_type == "documento"
        assert derivative.mime_type == "application/json"

    def test_save_jpeg_structure_grid_derivative_registers_all_inputs(
        self, db_session, sample_case, test_user, sample_evidence, tmp_path
    ):
        from app.config import get_settings
        from services.derivative_service import DerivativeService

        settings = get_settings()
        extra = Evidence(
            id=uuid.uuid4(),
            case_id=sample_case.id,
            filename="q2.jpg",
            original_filename="q2.jpg",
            file_path=str(tmp_path / "q2.jpg"),
            file_size=128,
            file_type="imagem",
            mime_type="image/jpeg",
            sha256="c" * 64,
            uploaded_by=test_user.id,
        )
        ref_ev = Evidence(
            id=uuid.uuid4(),
            case_id=sample_case.id,
            filename="ref.jpg",
            original_filename="ref.jpg",
            file_path=str(tmp_path / "ref.jpg"),
            file_size=128,
            file_type="imagem",
            mime_type="image/jpeg",
            sha256="d" * 64,
            uploaded_by=test_user.id,
            extra_metadata={"is_reference": True},
        )
        db_session.add(extra)
        db_session.add(ref_ev)
        db_session.commit()

        q_ids = [sample_evidence.id, extra.id]
        r_ids = [ref_ev.id]
        job_id = uuid.uuid4()
        result_dir = Path(settings.RESULTS_DIR) / str(job_id)
        result_dir.mkdir(parents=True, exist_ok=True)
        params = {
            "mode": "with_reference",
            "questioned_evidence_ids": [str(i) for i in q_ids],
            "reference_evidence_ids": [str(i) for i in r_ids],
        }
        receipt = _seed_job_preview(
            job_id=job_id,
            result_dir=result_dir,
            technique="jpeg_structure_compare",
            parameters=params,
            extra_result={
                "mode": "with_reference",
                "artifact_kind": "positional_grid",
                "reference_count": 1,
                "questioned_count": 2,
            },
            evidence_sha256=sample_evidence.sha256,
        )
        (result_dir / "jpeg_structure_grid.json").write_text(
            '{"mode":"with_reference","artifact_kind":"positional_grid","reference_count":1,"questioned_count":2}',
            encoding="utf-8",
        )

        job = AnalysisJob(
            id=job_id,
            evidence_id=sample_evidence.id,
            technique="jpeg_structure_compare",
            status="completed",
            parameters=params,
            result_path=str(result_dir),
            runtime_manifest=receipt,
            created_by=test_user.id,
        )
        db_session.add(job)
        db_session.commit()

        derivative = DerivativeService(db_session).save_from_job(
            job_id=job_id,
            artifact_filename="jpeg_structure_grid.json",
            user_id=test_user.id,
            label="jpeg_grade_test",
        )

        assert "Grade posicional JPEG" in derivative.extra_metadata["procedure_summary"]
        assert len(derivative.extra_metadata["parent_inputs"]) == 3
        assert derivative.file_type == "documento"
        assert derivative.mime_type == "application/json"


class TestDerivativeEndpoint:
    def test_save_derivative_http(
        self, client, db_session, sample_case, test_user, sample_evidence, auth_headers
    ):
        from app.config import get_settings

        settings = get_settings()
        job_id = uuid.uuid4()
        result_dir = Path(settings.RESULTS_DIR) / str(job_id)
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
        result_dir = Path(settings.RESULTS_DIR) / str(job_id)
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
        result1 = Path(settings.RESULTS_DIR) / str(job1_id)
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
        result2 = Path(settings.RESULTS_DIR) / str(job2_id)
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
