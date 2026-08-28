"""Job service — orchestrates forensic analysis jobs."""

import logging
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.config import get_settings
from core.plugin_registry import PluginRegistry
from core.job_artifacts import cleanup_ephemeral_artifact_sources, stage_plugin_artifacts
from core.job_staging import inject_job_staging
from core.plugin_contracts import reproducibility_manifest
from core.reproducibility import (
    build_job_execution_receipt,
    build_reproducibility_record,
    build_runtime_manifest,
    compare_execution_receipt,
    compare_reproduction,
    load_job_execution_receipt,
)
from core.progress import JobProgressReporter, inject_progress
from core.technique_ids import resolve_technique_id
from core.evidence_role_resolver import resolve_evidence_parameters
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

    @staticmethod
    def _validate_jpeg_structure_paths(parameters: Dict[str, Any]) -> None:
        """Ensure all image paths in jpeg_structure_compare are actual JPEG files."""
        from core.metadata.jpeg_structure_dump import is_jpeg_file

        for key in ("questioned_paths", "reference_paths", "evidence_paths"):
            for path in parameters.get(key) or []:
                if not is_jpeg_file(path):
                    label = "Referencia" if key == "reference_paths" else "Evidencia"
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                        detail=f"{label} {Path(path).name} nao e JPEG",
                    )

    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()
        self.registry = PluginRegistry()
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
        evidence = self.db.query(Evidence).filter(
            Evidence.id == evidence_id, Evidence.deleted_at.is_(None)
        ).first()
        if not evidence:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Evidencia nao encontrada",
            )

        # Jobs cannot be submitted on closed/pending-closure cases.
        assert_case_not_closed(evidence.case)

        technique = resolve_technique_id(technique)

        if technique not in self.registry.PLUGINS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Tecnica '{technique}' nao disponivel",
            )
        plugin_cls = self.registry.PLUGINS[technique]

        # Resolve UI parameter aliases to plugin schema before validation.
        resolved_parameters = resolve_evidence_parameters(
            self.db,
            dict(parameters or {}),
            plugin_cls().parameters_schema,
            technique=technique,
        )
        if technique == "jpeg_structure_compare":
            self._validate_jpeg_structure_paths(resolved_parameters)

        plugin = plugin_cls()
        if evidence.file_type not in plugin.supported_types:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    f"Tecnica '{technique}' nao suporta evidencias do tipo "
                    f"'{evidence.file_type}'. Tipos suportados: {plugin.supported_types}"
                ),
            )

        valid, msg = plugin.validate_parameters(resolved_parameters)
        if not valid:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Parametros invalidos: {msg}",
            )

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
                # Prefer plugin-native runtime check; else technique_runtime_status.
                if hasattr(plugin, "is_runtime_available") and callable(plugin.is_runtime_available):
                    available, reason = plugin.is_runtime_available()
                else:
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

        plugin_cls = self.registry.PLUGINS.get(resolve_technique_id(job.technique))
        if not plugin_cls:
            return parameters

        # Only re-resolve if evidence roles have not been resolved yet.
        has_resolved_paths = any(
            k.endswith("_path") or k.endswith("_paths")
            for k in parameters.keys()
            if any(
                role in k
                for role in ("reference", "questioned", "evidence", "fingerprint")
            )
        )
        if has_resolved_paths:
            return parameters

        parameters = resolve_evidence_parameters(
            self.db,
            parameters,
            plugin_cls().parameters_schema,
            technique=job.technique,
        )
        if job.technique == "jpeg_structure_compare":
            self._validate_jpeg_structure_paths(parameters)

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
            "primary_artifact": reproducibility_manifest(
                resolve_technique_id(job.technique)
            ).get("primary"),
            **comparison,
        }

    def run_job(self, job_id: uuid.UUID) -> AnalysisJob:
        """Execute a job synchronously (used by Celery worker).

        Finds the plugin, runs analysis, updates status, and stores results.
        """
        import time

        t0 = time.monotonic()
        job = self.get_job(job_id)
        evidence = self.db.query(Evidence).filter(Evidence.id == job.evidence_id).first()

        reporter = JobProgressReporter(job.id, self.db)

        job.status = "running"
        job.progress = 0
        job.progress_message = "Iniciando analise"
        job.started_at = datetime.now(timezone.utc)
        self.db.commit()
        logger.info(
            "TIMING run_job=%s tecnica=%s status_to_running=%.2fs",
            job_id, job.technique, time.monotonic() - t0,
        )
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

            # Canonical artifact hash for reproducibility verification.
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
            logger.info(
                "TIMING run_job=%s tecnica=%s total=%.2fs",
                job_id, job.technique, time.monotonic() - t0,
            )
            reporter(100, "Concluido")

        except Exception as exc:
            from core.gpu_inference import GpuVramExhausted

            if isinstance(exc, GpuVramExhausted):
                # OOM: purge completo, re-enfileira para outra GPU.
                from core.gpu_inference import purge_foreign_gpu_model_caches

                purge_foreign_gpu_model_caches(include_trufor=True)
                job.progress_message = (
                    "VRAM insuficiente nesta GPU; tentando outra GPU..."
                )
                job.error_message = str(exc)
                self.db.commit()
                self.db.refresh(job)
                raise

            job.status = "failed"
            job.progress = 0
            job.progress_message = str(exc)[:512]
            job.error_message = str(exc)
            job.completed_at = datetime.now(timezone.utc)
            self.db.commit()
            logger.info(
                "TIMING run_job=%s tecnica=%s failed_after=%.2fs",
                job_id, job.technique, time.monotonic() - t0,
            )
            self.db.refresh(job)
            return job

        self.db.refresh(job)
        return job
