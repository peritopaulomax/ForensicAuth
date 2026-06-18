"""Job progress reporting for forensic analysis plugins."""

from __future__ import annotations

import time
import uuid
from typing import Any, Callable, Dict, Optional

from sqlalchemy.orm import Session

from models.analysis_job import AnalysisJob

ProgressCallback = Callable[[int, str], None]

_PROGRESS_KEY = "_on_progress"


def inject_progress(parameters: Dict[str, Any], callback: ProgressCallback) -> Dict[str, Any]:
    """Return a copy of parameters with the progress callback attached."""
    out = dict(parameters)
    out[_PROGRESS_KEY] = callback
    return out


def pop_progress_callback(parameters: Dict[str, Any]) -> Optional[ProgressCallback]:
    """Remove and return the progress callback (mutates parameters)."""
    cb = parameters.pop(_PROGRESS_KEY, None)
    return cb if callable(cb) else None


def report_progress(
    callback: Optional[ProgressCallback],
    percent: int,
    message: str,
) -> None:
    if callback is not None:
        callback(max(0, min(100, int(percent))), message)


class JobProgressReporter:
    """Persists progress to analysis_jobs (throttled commits on the job session)."""

    def __init__(self, job_id: uuid.UUID, db: Session) -> None:
        self.job_id = job_id
        self.db = db
        self._last_pct = -1
        self._last_write = 0.0

    def __call__(self, percent: int, message: str) -> None:
        percent = max(0, min(100, int(percent)))
        message = (message or "")[:512]
        now = time.monotonic()
        if percent == self._last_pct and (now - self._last_write) < 0.25:
            return
        if abs(percent - self._last_pct) < 1 and (now - self._last_write) < 0.4:
            return

        job = self.db.query(AnalysisJob).filter(AnalysisJob.id == self.job_id).first()
        if job is None:
            return
        job.progress = percent
        job.progress_message = message
        self.db.commit()
        self._last_pct = percent
        self._last_write = now
