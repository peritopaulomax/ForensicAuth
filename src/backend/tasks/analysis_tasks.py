"""Celery tasks for forensic analysis."""

import uuid

from celery.exceptions import MaxRetriesExceededError, Retry

from app.celery_app import celery_app
from app.database import SessionLocal
from core.gpu_inference import ML_GPU_TECHNIQUES, ml_gpu_job_slot
from core.gpu_lock import gpu_distributed_lock
from services.job_service import JobService


def _execute_job(self, job_id: str) -> dict:
    """Shared execution logic for CPU and GPU forensic analysis tasks."""
    db = SessionLocal()
    try:
        service = JobService(db)
        job = service.get_job(uuid.UUID(job_id))
        technique = job.technique

        def _run() -> object:
            return service.run_job(uuid.UUID(job_id))

        if technique in ML_GPU_TECHNIQUES:
            with gpu_distributed_lock(blocking=True) as acquired:
                if not acquired:
                    raise self.retry(countdown=30, exc=RuntimeError("GPU lock timeout"))
                with ml_gpu_job_slot(technique):
                    job = _run()
        else:
            job = _run()

        return {
            "status": job.status,
            "job_id": str(job.id),
            "result_path": job.result_path,
            "result_sha256": job.result_sha256,
        }
    except Retry:
        raise
    except MaxRetriesExceededError:
        raise
    except Exception as exc:
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
        raise
    finally:
        db.close()


@celery_app.task(bind=True, max_retries=3, name="tasks.analysis_tasks.run_forensic_analysis")
def run_forensic_analysis(self, job_id: str) -> dict:
    """Legacy dispatcher: executes CPU or GPU task based on technique.

    Prefer dispatching via run_forensic_analysis_cpu/gpu directly.
    """
    db = SessionLocal()
    try:
        service = JobService(db)
        job = service.get_job(uuid.UUID(job_id))
        technique = job.technique
    finally:
        db.close()

    if technique in ML_GPU_TECHNIQUES:
        return run_forensic_analysis_gpu.delay(job_id).get(
            timeout=celery_app.conf.task_annotations["tasks.analysis_tasks.run_forensic_analysis_gpu"]["time_limit"] + 30
        )
    return run_forensic_analysis_cpu.delay(job_id).get(
        timeout=celery_app.conf.task_annotations["tasks.analysis_tasks.run_forensic_analysis_cpu"]["time_limit"] + 30
    )


@celery_app.task(bind=True, max_retries=3)
def run_forensic_analysis_cpu(self, job_id: str) -> dict:
    """Execute a CPU forensic analysis job (10 min hard timeout)."""
    return _execute_job(self, job_id)


@celery_app.task(bind=True, max_retries=3)
def run_forensic_analysis_gpu(self, job_id: str) -> dict:
    """Execute a GPU forensic analysis job (1h hard timeout)."""
    return _execute_job(self, job_id)
