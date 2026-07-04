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


async def run_daily_preview_cleanup(settings: Settings) -> None:
    """Run preview cleanup once per day at the configured local hour."""
    hour = int(getattr(settings, "JOB_PREVIEW_CLEANUP_HOUR", 2))
    while True:
        await asyncio.sleep(_seconds_until_hour(hour))
        try:
            removed = await asyncio.to_thread(cleanup_expired_job_previews)
            if removed:
                logger.info("Faxina diaria de previews removeu %s diretorios", removed)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Falha na faxina diaria de previews")


def start_daily_preview_cleanup(settings: Settings) -> asyncio.Task | None:
    """Start the API-process cleanup task if enabled."""
    if not getattr(settings, "JOB_PREVIEW_DAILY_CLEANUP", True):
        return None
    if getattr(settings, "FORENSICAUTH_PROCESS_ROLE", "api") != "api":
        return None
    return asyncio.create_task(run_daily_preview_cleanup(settings))
