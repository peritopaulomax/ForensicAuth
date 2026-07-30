"""Daily scheduler for job preview cleanup."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from app.config import Settings
from core.preview_cleanup import cleanup_expired_job_previews

logger = logging.getLogger(__name__)


def _seconds_until_hour(hour: int) -> float:
    now = datetime.now().astimezone()
    target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return max(1.0, (target - now).total_seconds())


def run_preview_cleanup_once() -> int:
    """Open a DB session and sweep expired previews (nested + legacy paths)."""
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        removed = cleanup_expired_job_previews(db)
        logger.info(
            "Limpeza de previews concluiu: %s diretorio(s) removido(s)",
            removed,
        )
        return removed
    except Exception:
        logger.exception("Falha na limpeza de previews")
        # Filesystem-only fallback if DB path fails mid-flight.
        try:
            return cleanup_expired_job_previews(None)
        except Exception:
            logger.exception("Fallback filesystem de limpeza de previews tambem falhou")
            return 0
    finally:
        db.close()


async def run_daily_preview_cleanup(settings: Settings) -> None:
    """Run preview cleanup once per day at the configured local hour."""
    hour = int(getattr(settings, "JOB_PREVIEW_CLEANUP_HOUR", 2))
    # Startup pass: clear anything already expired without waiting for 02:00.
    try:
        removed = await asyncio.to_thread(run_preview_cleanup_once)
        if removed:
            logger.info(
                "Limpeza inicial de previews removeu %s diretorio(s)",
                removed,
            )
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Falha na limpeza inicial de previews")

    while True:
        await asyncio.sleep(_seconds_until_hour(hour))
        try:
            removed = await asyncio.to_thread(run_preview_cleanup_once)
            if removed:
                logger.info(
                    "Limpeza diaria de previews removeu %s diretorio(s)",
                    removed,
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Falha na limpeza diaria de previews")


def start_daily_preview_cleanup(settings: Settings) -> asyncio.Task | None:
    """Start the API-process cleanup task if enabled."""
    if not getattr(settings, "JOB_PREVIEW_DAILY_CLEANUP", True):
        logger.info("Limpeza diaria de previews desabilitada (JOB_PREVIEW_DAILY_CLEANUP=false)")
        return None
    role = getattr(settings, "FORENSICAUTH_PROCESS_ROLE", "api")
    if role != "api":
        logger.info(
            "Limpeza diaria de previews so roda no processo api (role=%s)",
            role,
        )
        return None
    retention = int(getattr(settings, "JOB_PREVIEW_RETENTION_DAYS", 0))
    hour = int(getattr(settings, "JOB_PREVIEW_CLEANUP_HOUR", 2))
    logger.info(
        "Agendando limpeza diaria de previews (retencao=%s dia(s), hora local=%02d:00)",
        retention,
        hour,
    )
    return asyncio.create_task(run_daily_preview_cleanup(settings))
