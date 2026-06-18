"""Celery worker startup — ML warmup only on worker-gpu role."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def should_run_ml_warmup() -> bool:
    from app.config import get_settings

    settings = get_settings()
    if settings.FORENSICAUTH_PROCESS_ROLE != "worker-gpu":
        return False
    if not settings.ML_WARMUP_ON_STARTUP:
        return False
    return bool(settings.GPU_AVAILABLE)


def schedule_worker_warmups() -> None:
    """Schedule Effort/SAFE/CAMO/IAPL warmups (idempotent per process)."""
    from app.config import get_settings

    settings = get_settings()
    if not should_run_ml_warmup():
        logger.info(
            "ML warmup ignorado (role=%s, ml_warmup=%s, gpu=%s)",
            settings.FORENSICAUTH_PROCESS_ROLE,
            settings.ML_WARMUP_ON_STARTUP,
            settings.GPU_AVAILABLE,
        )
        return

    from core.legacy.camo.camo_warmup import schedule_camo_warmup
    from core.legacy.effort.effort_warmup import schedule_effort_warmup
    from core.legacy.iapl.iapl_warmup import schedule_iapl_warmup
    from core.legacy.safe.safe_warmup import schedule_safe_warmup

    schedule_effort_warmup()
    schedule_safe_warmup()
    schedule_camo_warmup()
    schedule_iapl_warmup()
    logger.info("ML warmup agendado no worker-gpu")
