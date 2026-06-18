"""Background execution of analysis jobs (dev thread or Celery)."""

from __future__ import annotations

import logging
import threading
import uuid

from app.config import get_settings
from app.database import SessionLocal
from core.gpu_inference import ml_gpu_job_slot
from core.job_dispatch import queue_for_technique
from services.job_service import JobService

logger = logging.getLogger(__name__)


def _uses_celery_backend() -> bool:
    settings = get_settings()
    return "sqlite" not in settings.DATABASE_URL.lower()


def _record_dispatch_queue(job_id: uuid.UUID, queue: str) -> None:
    db = SessionLocal()
    try:
        service = JobService(db)
        job = service.get_job(job_id)
        manifest = dict(job.runtime_manifest or {})
        manifest["dispatch_queue"] = queue
        job.runtime_manifest = manifest
        db.commit()
    except Exception:
        logger.exception("Falha ao registrar dispatch_queue para job %s", job_id)
        db.rollback()
    finally:
        db.close()


def run_job_in_background(job_id: uuid.UUID) -> None:
    """Queue job execution without blocking the HTTP request."""
    settings = get_settings()
    jid = str(job_id)

    db = SessionLocal()
    technique = ""
    try:
        service = JobService(db)
        job = service.get_job(job_id)
        technique = job.technique
        queue = queue_for_technique(technique)
    finally:
        db.close()

    if _uses_celery_backend():
        try:
            from tasks.analysis_tasks import run_forensic_analysis

            _record_dispatch_queue(job_id, queue)
            run_forensic_analysis.apply_async(args=[jid], queue=queue)
            logger.info("Job %s enfileirado em %s (tecnica=%s)", jid, queue, technique)
            return
        except Exception as exc:
            logger.warning("Celery indisponivel (%s); usando thread local.", exc)

    thread = threading.Thread(target=_run_job_sync, args=(jid,), daemon=True)
    thread.start()


def _run_job_sync(job_id: str) -> None:
    db = SessionLocal()
    try:
        service = JobService(db)
        job = service.get_job(uuid.UUID(job_id))
        with ml_gpu_job_slot(job.technique):
            service.run_job(uuid.UUID(job_id))
    except Exception:
        logger.exception("Falha ao executar job %s", job_id)
    finally:
        db.close()
