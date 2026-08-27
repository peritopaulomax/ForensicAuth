"""Celery tasks for forensic analysis."""

import uuid
from datetime import datetime, timezone

from celery.exceptions import MaxRetriesExceededError, Retry

from app.celery_app import celery_app
from app.database import SessionLocal
from core.gpu_inference import ML_GPU_TECHNIQUES, ml_gpu_job_slot
from core.gpu_lock import gpu_distributed_lock
from services.job_service import JobService


def _gpu_worker_count() -> int:
    """Return the number of GPU workers currently online."""
    try:
        inspect = celery_app.control.inspect()
        active = inspect.active_queues()
        if not active:
            return 1
        count = sum(
            1
            for _worker, queues in active.items()
            if any(q.get("name") == "gpu" for q in queues)
        )
        return max(count, 1)
    except Exception:
        return 1


def _execute_job(self, job_id: str) -> dict:
    """Shared execution logic for CPU and GPU forensic analysis tasks."""
    from app.config import get_settings
    from core.gpu_inference import GpuVramExhausted, cuda_memory_snapshot

    db = SessionLocal()
    try:
        service = JobService(db)
        job = service.get_job(uuid.UUID(job_id))
        technique = job.technique
        settings = get_settings()

        def _run() -> object:
            return service.run_job(uuid.UUID(job_id))

        if technique in ML_GPU_TECHNIQUES:
            # Se este worker exclui a tecnica, re-enfileira para outra GPU.
            excluded = {
                t.strip()
                for t in settings.GPU_EXCLUDED_TECHNIQUES.split(",")
                if t.strip()
            }
            if technique in excluded and self.request.retries < self.max_retries:
                raise self.retry(
                    countdown=30,
                    exc=RuntimeError(
                        f"Tecnica {technique} excluida neste worker GPU; "
                        "re-enfileirando para outra GPU"
                    ),
                )
            # Pre-check: sem VRAM minima, re-enfileira sem nem tentar — outro
            # worker GPU (ou o mesmo, ja livre) pega a task no retry.
            snap = cuda_memory_snapshot()
            free_mb = snap.get("free_mb")
            if (
                settings.GPU_AVAILABLE
                and free_mb is not None
                and free_mb < settings.GPU_MIN_FREE_MB
                and self.request.retries < self.max_retries
            ):
                raise self.retry(
                    countdown=45,
                    exc=GpuVramExhausted(
                        f"VRAM livre ({free_mb} MiB) abaixo do minimo "
                        f"({settings.GPU_MIN_FREE_MB} MiB); aguardando GPU liberar"
                    ),
                )
            with gpu_distributed_lock(blocking=True) as acquired:
                if not acquired:
                    raise self.retry(countdown=30, exc=RuntimeError("GPU lock timeout"))
                with ml_gpu_job_slot(technique):
                    try:
                        job = _run()
                    except GpuVramExhausted as exc:
                        # OOM persistiu apos purge+retry no pipeline: devolve a
                        # task para a fila para outra GPU (ou esta, ja livre).
                        if self.request.retries < self.max_retries:
                            raise self.retry(countdown=45, exc=exc) from exc
                        # Todas as GPUs falharam: mensagem clara para o usuario.
                        job.status = "failed"
                        job.progress_message = (
                            "Nenhuma GPU com VRAM suficiente para executar esta "
                            "tecnica. Todas as GPUs disponiveis falharam por OOM."
                        )
                        job.error_message = str(exc)
                        job.completed_at = datetime.now(timezone.utc)
                        db.commit()
                        db.refresh(job)
                        return {
                            "status": job.status,
                            "job_id": str(job.id),
                            "result_path": None,
                            "result_sha256": None,
                        }
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


@celery_app.task(bind=True, name="tasks.analysis_tasks.run_forensic_analysis")
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


@celery_app.task(bind=True)
def run_forensic_analysis_cpu(self, job_id: str) -> dict:
    """Execute a CPU forensic analysis job (10 min hard timeout)."""
    return _execute_job(self, job_id)


@celery_app.task(bind=True)
def run_forensic_analysis_gpu(self, job_id: str) -> dict:
    """Execute a GPU forensic analysis job (1h hard timeout).

    max_retries is computed dynamically from the number of online GPU workers.
    """
    self.max_retries = _gpu_worker_count()
    return _execute_job(self, job_id)
