"""Throttled preview cleanup — avoid scanning all jobs on every analysis run."""

from __future__ import annotations

import time

from sqlalchemy.orm import Session

from core.preview_cleanup import cleanup_expired_job_previews

_LAST_CLEANUP_MONO: float = 0.0
CLEANUP_MIN_INTERVAL_SEC: float = 3600.0


def maybe_cleanup_expired_job_previews(db: Session | None = None) -> int:
    """Run preview cleanup at most once per hour per process."""
    global _LAST_CLEANUP_MONO
    now = time.monotonic()
    if _LAST_CLEANUP_MONO > 0 and now - _LAST_CLEANUP_MONO < CLEANUP_MIN_INTERVAL_SEC:
        return 0
    _LAST_CLEANUP_MONO = now
    return cleanup_expired_job_previews(db)


def reset_cleanup_throttle_for_tests() -> None:
    """Allow tests to force immediate cleanup."""
    global _LAST_CLEANUP_MONO
    _LAST_CLEANUP_MONO = 0.0
