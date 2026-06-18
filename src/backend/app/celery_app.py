"""Celery application configuration."""

from celery import Celery
from celery.signals import worker_process_init

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "forensicauth",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["tasks.analysis_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="America/Sao_Paulo",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,
    task_soft_time_limit=3300,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_routes={
        "tasks.analysis_tasks.run_forensic_analysis": {"queue": "celery"},
    },
)


@worker_process_init.connect
def _on_worker_process_init(**_kwargs) -> None:
    """Warmup ML models only in worker-gpu child processes."""
    from app.worker_bootstrap import schedule_worker_warmups

    schedule_worker_warmups()
