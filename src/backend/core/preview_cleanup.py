"""Cleanup expired job preview directories."""

from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.config import get_settings
from models.analysis_job import AnalysisJob
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def _parse_completed_at(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def cleanup_expired_job_previews(db: Session | None = None) -> int:
    """Delete expired preview folders.

    Promoted derivatives are persisted under DERIVATIVES_DIR with custody records,
    so the job preview directory remains disposable.
    """
    settings = get_settings()
    retention_days = int(getattr(settings, "JOB_PREVIEW_RETENTION_DAYS", 0))
    cutoff = (
        datetime.now(timezone.utc) - timedelta(days=retention_days)
        if retention_days > 0
        else datetime.now(timezone.utc)
    )
    results_root = Path(settings.RESULTS_DIR).resolve()
    removed = 0

    if db is not None:
        jobs = (
            db.query(AnalysisJob)
            .filter(AnalysisJob.status == "completed", AnalysisJob.completed_at.isnot(None))
            .all()
        )
        for job in jobs:
            completed = _parse_completed_at(job.completed_at)
            if completed is None or completed > cutoff:
                continue
            if _remove_job_preview_dir(results_root, job.id):
                removed += 1
        return removed

    if not results_root.is_dir():
        return 0

    for child in results_root.iterdir():
        if not child.is_dir():
            continue
        result_json = child / "result.json"
        if not result_json.is_file():
            continue
        try:
            payload = json.loads(result_json.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not payload.get("preview"):
            continue
        mtime = datetime.fromtimestamp(result_json.stat().st_mtime, tz=timezone.utc)
        if mtime > cutoff:
            continue
        shutil.rmtree(child, ignore_errors=True)
        removed += 1
        logger.info("Preview expirado removido: %s", child)

    return removed

def _remove_job_preview_dir(results_root: Path, job_id) -> bool:
    target = results_root / str(job_id)
    if not target.is_dir():
        return False
    shutil.rmtree(target, ignore_errors=True)
    logger.info("Preview do job removido: %s", target)
    return True
