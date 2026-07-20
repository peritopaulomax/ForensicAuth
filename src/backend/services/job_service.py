"""Job service — orchestrates forensic analysis jobs."""

import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.config import get_settings
from core.plugin_registry import PluginRegistry
from core.job_artifacts import cleanup_ephemeral_artifact_sources, stage_plugin_artifacts
from core.job_staging import inject_job_staging
from core.reproducibility import (
    REPRODUCIBILITY_REGISTRY,
    build_job_execution_receipt,
    build_reproducibility_record,
    build_runtime_manifest,
    compare_execution_receipt,
    compare_reproduction,
    load_job_execution_receipt,
)
from core.progress import JobProgressReporter, inject_progress
from core.technique_ids import resolve_technique_id
from core.technique_runtime import technique_runtime_status
from models.analysis_job import AnalysisJob
from models.evidence import Evidence
from services.case_access import assert_case_not_closed


def build_job_result_dir(
    results_dir: str | Path,
    case_id: uuid.UUID,
    evidence_id: uuid.UUID,
    job_id: uuid.UUID,
) -> Path:
    """Return canonical result directory for a job: RESULTS_DIR/case/evidence/job."""
    return Path(results_dir) / str(case_id) / str(evidence_id) / str(job_id)


class JobService:
    """Service for submitting, tracking, and executing forensic analysis jobs."""

    def _resolve_evidence_paths_labels(
        self,
        evidence_ids: list[Any],
        *,
        expected_file_type: str | None = None,
    ) -> tuple[list[str], list[str]]:
        paths: list[str] = []
        labels: list[str] = []
        for ev_id in evidence_ids:
            try:
                ev_uuid = ev_id if isinstance(ev_id, uuid.UUID) else uuid.UUID(str(ev_id))
            except (ValueError, TypeError):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=f"ID de evidencia invalido: {ev_id}",
                )
            ev = self.db.query(Evidence).filter(
                Evidence.id == ev_uuid,
                Evidence.deleted_at.is_(None),
            ).first()
            if not ev:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=f"Evidencia nao encontrada: {ev_id}",
                )
            if expected_file_type and ev.file_type != expected_file_type:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=f"Evidencia {ev.original_filename} nao e do tipo {expected_file_type}",
                )
            paths.append(ev.file_path)
            labels.append(ev.original_filename or ev.filename)
        return paths, labels

    def _resolve_pdf_structure_similarity_params(
        self, parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        q_paths, q_labels = self._resolve_evidence_paths_labels(
            list(parameters.get("questioned_evidence_ids") or []),
            expected_file_type="pdf",
        )
        out: Dict[str, Any] = {
            "questioned_paths": q_paths,
            "questioned_labels": q_labels,
        }
        if parameters.get("mode") == "with_reference":
            r_paths, r_labels = self._resolve_evidence_paths_labels(
                list(parameters.get("reference_evidence_ids") or []),
                expected_file_type="pdf",
            )
            out["reference_paths"] = r_paths
            out["reference_labels"] = r_labels
        else:
            out["reference_paths"] = []
            out["reference_labels"] = []
        return out

    def _resolve_jpeg_structure_compare_params(
        self, parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        from core.metadata.jpeg_structure_dump import is_jpeg_file

        mode = parameters.get("mode", "positional")
        if mode in ("with_reference", "all_pairs"):
            q_ids = list(parameters.get("questioned_evidence_ids") or [])
            q_paths, q_labels = self._resolve_evidence_paths_labels(
                q_ids,
                expected_file_type="imagem",
            )
            for path in q_paths:
                if not is_jpeg_file(path):
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                        detail=f"Evidencia {Path(path).name} nao e JPEG",
                    )
            out: Dict[str, Any] = {
                "questioned_paths": q_paths,
                "questioned_labels": q_labels,
                "questioned_evidence_ids": [str(e) for e in q_ids],
            }
            if mode == "with_reference":
                r_ids = list(parameters.get("reference_evidence_ids") or [])
                r_paths, r_labels = self._resolve_evidence_paths_labels(
                    r_ids,
                    expected_file_type="imagem",
                )
                for path in r_paths:
                    if not is_jpeg_file(path):
                        raise HTTPException(
                            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail=f"Referencia {Path(path).name} nao e JPEG",
                        )
                out["reference_paths"] = r_paths
                out["reference_labels"] = r_labels
                out["reference_evidence_ids"] = [str(e) for e in r_ids]
            else:
                out["reference_paths"] = []
                out["reference_labels"] = []
                out["reference_evidence_ids"] = []
            return out

        ev_ids = list(parameters.get("evidence_ids") or [])
        paths, labels = self._resolve_evidence_paths_labels(
            ev_ids,
            expected_file_type="imagem",
        )
        for path in paths:
            if not is_jpeg_file(path):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=f"Evidencia {Path(path).name} nao e JPEG",
                )
        return {
            "evidence_paths": paths,
            "evidence_labels": labels,
            "evidence_ids": [str(e) for e in ev_ids],
        }

    def _resolve_isomedia_compare_params(
        self, parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        q_paths, q_labels = self._resolve_evidence_paths_labels(
            list(parameters.get("questioned_evidence_ids") or []),
            expected_file_type="video",
        )
        out: Dict[str, Any] = {
            "questioned_paths": q_paths,
            "questioned_labels": q_labels,
        }
        if parameters.get("mode") == "with_reference":
            r_paths, r_labels = self._resolve_evidence_paths_labels(
                list(parameters.get("reference_evidence_ids") or []),
                expected_file_type="video",
            )
            out["reference_paths"] = r_paths
            out["reference_labels"] = r_labels
        else:
            out["reference_paths"] = []
            out["reference_labels"] = []
        return out

    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()
        self.registry = PluginRegistry()
        # Discover plugins from the plugins directory
        plugins_dir = Path(__file__).parent.parent / "core" / "plugins"
        if plugins_dir.exists():
            self.registry.discover_and_register(str(plugins_dir))

    def submit_job(
        self,
        evidence_id: uuid.UUID,
        technique: str,
        parameters: Dict[str, Any],
        user_id: uuid.UUID,
    ) -> AnalysisJob:
        """Submit a new analysis job.

        Validates evidence existence, technique availability, and parameters.
        Creates the job record and returns it.
        """
        # 1. Validate evidence exists
        evidence = self.db.query(Evidence).filter(
            Evidence.id == evidence_id, Evidence.deleted_at.is_(None)
        ).first()
        if not evidence:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Evidencia nao encontrada",
            )

        # Validate case state: jobs cannot be submitted on closed/pending-closure cases
        assert_case_not_closed(evidence.case)

        technique = resolve_technique_id(technique)

        # 2. Validate technique exists in registry
        if technique not in self.registry.PLUGINS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Tecnica '{technique}' nao disponivel",
            )

        # 2.5 Resolve frontend-friendly params before plugin validation
        resolved_parameters = dict(parameters or {})
        if technique == "dct_quantization" and resolved_parameters.get("mode") == "reference":
            ref_ev_id = resolved_parameters.get("reference_evidence_id")
            if ref_ev_id:
                try:
                    ref_ev_uuid = ref_ev_id if isinstance(ref_ev_id, uuid.UUID) else uuid.UUID(str(ref_ev_id))
                except (ValueError, TypeError):
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                        detail="Parametros invalidos: reference_evidence_id invalido",
                    )
                ref_ev = self.db.query(Evidence).filter(
                    Evidence.id == ref_ev_uuid,
                    Evidence.deleted_at.is_(None),
                ).first()
                if not ref_ev:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                        detail="Parametros invalidos: reference_evidence_id nao encontrado",
                    )
                resolved_parameters["reference_path"] = ref_ev.file_path

        if technique == "prnu" and resolved_parameters.get("fingerprint_id"):
            case_id_raw = resolved_parameters.get("case_id")
            fp_id = resolved_parameters.get("fingerprint_id")
            if not case_id_raw:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="Parametros invalidos: case_id obrigatorio com fingerprint_id",
                )
            try:
                case_uuid = (
                    case_id_raw
                    if isinstance(case_id_raw, uuid.UUID)
                    else uuid.UUID(str(case_id_raw))
                )
            except (ValueError, TypeError):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="Parametros invalidos: case_id invalido",
                )
            from services.prnu_fingerprint_service import resolve_fingerprint_path

            fp_path = resolve_fingerprint_path(self.db, case_uuid, str(fp_id))
            resolved_parameters["fingerprint_path"] = str(fp_path)

        if technique == "pdf_structure_similarity":
            resolved_parameters.update(
                self._resolve_pdf_structure_similarity_params(resolved_parameters)
            )
        if technique == "isomedia_compare":
            resolved_parameters.update(
                self._resolve_isomedia_compare_params(resolved_parameters)
            )
        if technique == "jpeg_structure_compare":
            resolved_parameters.update(
                self._resolve_jpeg_structure_compare_params(resolved_parameters)
            )

        # 3. Validate media type compatibility
        plugin_cls = self.registry.PLUGINS[technique]
        plugin = plugin_cls()
        if evidence.file_type not in plugin.supported_types:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    f"Tecnica '{technique}' nao suporta evidencias do tipo "
                    f"'{evidence.file_type}'. Tipos suportados: {plugin.supported_types}"
                ),
            )

        # 4. Validate parameters
        valid, msg = plugin.validate_parameters(resolved_parameters)
        if not valid:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Parametros invalidos: {msg}",
            )

        # 4. Create job
        job = AnalysisJob(
            id=uuid.uuid4(),
            evidence_id=evidence_id,
            technique=technique,
            status="pending",
            parameters=resolved_parameters,
            created_by=user_id,
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)

        return job

    def get_job(self, job_id: uuid.UUID) -> AnalysisJob:
        """Retrieve a job by ID."""
        job = self.db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job nao encontrado",
            )
        return job

    def list_techniques(self) -> List[Dict[str, Any]]:
        """List all available forensic techniques from the plugin registry."""
        techniques = []
        for name, plugin_cls in self.registry.PLUGINS.items():
            plugin = plugin_cls()
            try:
                available, reason = technique_runtime_status(plugin.name)
            except Exception as exc:
                available, reason = False, f"Falha ao verificar runtime: {type(exc).__name__}: {exc}"
            techniques.append({
                "name": plugin.name,
                "supported_types": plugin.supported_types,
                "description": plugin.description,
                "parameters_schema": plugin.parameters_schema,
                "available": available,
                "unavailable_reason": reason if not available else None,
            })
        return techniques

    def _prepare_job_parameters(self, job: AnalysisJob) -> Dict[str, Any]:
        """Resolve stored parameters to runnable paths (DB lookups)."""
        parameters = dict(job.parameters or {})

        if job.technique == "dct_quantization" and parameters.get("mode") == "reference":
            ref_ev_id = parameters.get("reference_evidence_id")
            if ref_ev_id and not parameters.get("reference_path"):
                try:
                    ref_ev_uuid = (
                        ref_ev_id if isinstance(ref_ev_id, uuid.UUID) else uuid.UUID(str(ref_ev_id))
                    )
                except (ValueError, TypeError):
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                        detail="reference_evidence_id invalido",
                    )
                ref_ev = self.db.query(Evidence).filter(
                    Evidence.id == ref_ev_uuid,
                    Evidence.deleted_at.is_(None),
                ).first()
                if ref_ev:
                    parameters["reference_path"] = ref_ev.file_path

        if job.technique == "prnu" and parameters.get("fingerprint_id") and not parameters.get(
            "fingerprint_path"
        ):
            case_id_raw = parameters.get("case_id")
            fp_id = parameters.get("fingerprint_id")
            if case_id_raw and fp_id:
                try:
                    case_uuid = (
                        case_id_raw
                        if isinstance(case_id_raw, uuid.UUID)
                        else uuid.UUID(str(case_id_raw))
                    )
                except (ValueError, TypeError):
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                        detail="case_id invalido",
                    )
                from services.prnu_fingerprint_service import resolve_fingerprint_path

                fp_path = resolve_fingerprint_path(self.db, case_uuid, str(fp_id))
                parameters["fingerprint_path"] = str(fp_path)

        if job.technique == "pdf_structure_similarity" and not parameters.get("questioned_paths"):
            parameters.update(self._resolve_pdf_structure_similarity_params(parameters))
        if job.technique == "isomedia_compare" and not parameters.get("questioned_paths"):
            parameters.update(self._resolve_isomedia_compare_params(parameters))
        if job.technique == "jpeg_structure_compare":
            mode = parameters.get("mode", "positional")
            if mode in ("with_reference", "all_pairs"):
                if not parameters.get("questioned_paths"):
                    parameters.update(self._resolve_jpeg_structure_compare_params(parameters))
            elif not parameters.get("evidence_paths"):
                parameters.update(self._resolve_jpeg_structure_compare_params(parameters))

        return parameters

    def _execute_plugin_analysis(
        self,
        job: AnalysisJob,
        evidence: Optional[Evidence],
        *,
        progress_reporter: Optional[Any] = None,
        staging_dir: Path | None = None,
    ) -> Dict[str, Any]:
        """Run plugin only; does not persist job status or results."""
        technique_id = resolve_technique_id(job.technique)
        plugin_cls = self.registry.PLUGINS[technique_id]
        plugin = plugin_cls()
        evidence_path = evidence.file_path if evidence else ""
        parameters = self._prepare_job_parameters(job)
        if progress_reporter is not None:
            parameters = inject_progress(parameters, progress_reporter)
        if staging_dir is not None:
            parameters = inject_job_staging(parameters, staging_dir)
        result = plugin.analyze(evidence_path, parameters)
        if not result.get("success", True):
            raise RuntimeError(str(result.get("error", "Analise falhou")))
        return result

    @staticmethod
    def _json_default(obj: object) -> object:
        if isinstance(obj, Path):
            return str(obj)
        if hasattr(obj, "tolist"):
            size = getattr(obj, "size", 1)
            if size != 1:
                return obj.tolist()
        if hasattr(obj, "item"):
            try:
                return obj.item()
            except ValueError:
                if hasattr(obj, "tolist"):
                    return obj.tolist()
                raise
        if hasattr(obj, "tolist"):
            return obj.tolist()
        return str(obj)

    def reproduce_job(self, job_id: uuid.UUID) -> Dict[str, Any]:
        """Re-execute a completed job in isolation and compare artifact hashes."""
        job = self.get_job(job_id)
        if job.status != "completed":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Job deve estar completed para reproducao",
            )

        evidence = self.db.query(Evidence).filter(Evidence.id == job.evidence_id).first()
        if not evidence or not Path(evidence.file_path).is_file():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Evidencia do job nao encontrada em disco",
            )

        original_result: dict[str, Any] = {}
        result_path = build_job_result_dir(
            self.settings.RESULTS_DIR,
            job.evidence.case_id,
            job.evidence_id,
            job.id,
        ) / "result.json"
        if result_path.is_file():
            import json

            try:
                with open(result_path, encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    original_result = loaded
            except (json.JSONDecodeError, OSError):
                original_result = {}

        original_receipt = load_job_execution_receipt(
            original_result,
            job.runtime_manifest if isinstance(job.runtime_manifest, dict) else None,
        )

        with tempfile.TemporaryDirectory(prefix="forensicauth-repro-") as tmp:
            result_dir = Path(tmp)
            result = self._execute_plugin_analysis(job, evidence, staging_dir=result_dir)
            stage_plugin_artifacts(result, result_dir)
            current_runtime = build_runtime_manifest(
                app_version=self.settings.APP_VERSION,
                gpu_available=self.settings.GPU_AVAILABLE,
                models_dir=self.settings.MODELS_DIR,
                image_tag=self.settings.FORENSICAUTH_IMAGE_TAG,
                image_digest=self.settings.FORENSICAUTH_IMAGE_DIGEST,
                worker_queue=self.settings.FORENSICAUTH_WORKER_QUEUE,
                technique=job.technique,
            )
            reproduced_receipt = build_job_execution_receipt(
                technique=job.technique,
                result=result,
                runtime_manifest=current_runtime,
                job_id=str(job.id),
                parameters=job.parameters or {},
                input_evidence_sha256=evidence.sha256 if evidence else None,
            )

        if original_receipt:
            comparison = compare_execution_receipt(
                technique=job.technique,
                original_receipt=original_receipt,
                reproduced_receipt=reproduced_receipt,
                current_runtime=current_runtime,
            )
        else:
            reproduced_full = build_reproducibility_record(
                job.technique,
                result_dir,
                result,
                current_runtime,
            )
            comparison = compare_reproduction(
                technique=job.technique,
                determinism_profile=job.determinism_profile,
                original_artifact_sha256=job.artifact_sha256,
                reproduced_artifact_sha256=reproduced_full["artifact_sha256"],
                original_runtime=job.runtime_manifest if isinstance(job.runtime_manifest, dict) else None,
                current_runtime=current_runtime,
            )

        return {
            "job_id": str(job.id),
            "technique": job.technique,
            "evidence_id": str(job.evidence_id),
            "primary_artifact": REPRODUCIBILITY_REGISTRY.get(
                resolve_technique_id(job.technique), {}
            ).get("primary"),
            **comparison,
        }

    def run_job(self, job_id: uuid.UUID) -> AnalysisJob:
        """Execute a job synchronously (used by Celery worker).

        Finds the plugin, runs analysis, updates status, and stores results.
        """
        job = self.get_job(job_id)
        evidence = self.db.query(Evidence).filter(Evidence.id == job.evidence_id).first()

        reporter = JobProgressReporter(job.id, self.db)

        # Update status to running
        job.status = "running"
        job.progress = 0
        job.progress_message = "Iniciando analise"
        job.started_at = datetime.now(timezone.utc)
        self.db.commit()
        reporter(2, "Preparando plugin")

        try:
            reporter(5, f"Executando {job.technique}")
            result_dir = build_job_result_dir(
                self.settings.RESULTS_DIR,
                job.evidence.case_id,
                job.evidence_id,
                job.id,
            )
            result_dir.mkdir(parents=True, exist_ok=True)
            result = self._execute_plugin_analysis(
                job,
                evidence,
                progress_reporter=reporter,
                staging_dir=result_dir,
            )

            reporter(88, "Salvando preview")

            stage_plugin_artifacts(result, result_dir)
            cleanup_ephemeral_artifact_sources(result, result_dir)

            import hashlib
            import json

            # #region agent log
            try:
                import time as _time

                _mpbq = result.get("metric_peaks_by_quality")
                _dbg_payload = {
                    "sessionId": "5ac282",
                    "hypothesisId": "A",
                    "location": "job_service.py:run_job",
                    "message": "before build_job_execution_receipt",
                    "data": {
                        "technique": job.technique,
                        "has_metric_peaks": _mpbq is not None,
                        "metric_peak_key_types": (
                            [type(k).__name__ for k in _mpbq.keys()] if isinstance(_mpbq, dict) else []
                        ),
                    },
                    "timestamp": int(_time.time() * 1000),
                }
                _dbg_path = Path(__file__).resolve().parents[2] / ".cursor" / "debug-5ac282.log"
                with open(_dbg_path, "a", encoding="utf-8") as _df:
                    _df.write(json.dumps(_dbg_payload, default=str) + "\n")
            except Exception:
                pass
            # #endregion

            runtime_manifest = build_runtime_manifest(
                app_version=self.settings.APP_VERSION,
                gpu_available=self.settings.GPU_AVAILABLE,
                models_dir=self.settings.MODELS_DIR,
                image_tag=self.settings.FORENSICAUTH_IMAGE_TAG,
                image_digest=self.settings.FORENSICAUTH_IMAGE_DIGEST,
                worker_queue=self.settings.FORENSICAUTH_WORKER_QUEUE,
                technique=job.technique,
            )
            job_receipt = build_job_execution_receipt(
                technique=job.technique,
                result=result,
                runtime_manifest=runtime_manifest,
                job_id=str(job.id),
                parameters=job.parameters or {},
                input_evidence_sha256=evidence.sha256 if evidence else None,
            )
            result["job_receipt"] = job_receipt
            result["preview"] = True
            result["promoted"] = False
            result["effective_parameters"] = dict(job.parameters or {})

            result_path = result_dir / "result.json"
            with open(result_path, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2, default=self._json_default)

            result_path_hash = hashlib.sha256()
            with open(result_path, "rb") as f:
                result_path_hash.update(f.read())

            # Compute canonical artifact hash for reproducibility verification
            from core.reproducibility import compute_artifact_sha256

            artifact_sha256, _, _ = compute_artifact_sha256(
                job.technique, result_dir, result
            )

            job.status = "completed"
            job.progress = 100
            job.progress_message = "Concluido"
            job.result_path = str(result_dir)
            job.result_sha256 = result_path_hash.hexdigest()
            job.artifact_sha256 = artifact_sha256
            job.runtime_manifest = job_receipt
            job.determinism_profile = job_receipt.get("determinism_profile")
            job.completed_at = datetime.now(timezone.utc)
            self.db.commit()
            reporter(100, "Concluido")

        except Exception as exc:
            # #region agent log
            try:
                import json
                import time as _time

                _dbg_payload = {
                    "sessionId": "5ac282",
                    "hypothesisId": "A",
                    "location": "job_service.py:run_job:except",
                    "message": "job failed",
                    "data": {
                        "technique": job.technique,
                        "error": str(exc),
                        "error_type": type(exc).__name__,
                    },
                    "timestamp": int(_time.time() * 1000),
                }
                _dbg_path = Path(__file__).resolve().parents[2] / ".cursor" / "debug-5ac282.log"
                with open(_dbg_path, "a", encoding="utf-8") as _df:
                    _df.write(json.dumps(_dbg_payload, default=str) + "\n")
            except Exception:
                pass
            # #endregion
            job.status = "failed"
            job.progress = 0
            job.progress_message = str(exc)[:512]
            job.error_message = str(exc)
            job.completed_at = datetime.now(timezone.utc)
            self.db.commit()
            self.db.refresh(job)
            return job

        self.db.refresh(job)
        return job
