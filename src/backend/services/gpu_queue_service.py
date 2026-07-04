"""GPU job queue visibility for pending ML jobs."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from core.gpu_inference import ML_GPU_TECHNIQUES
from models.analysis_job import AnalysisJob

STALE_PENDING_GPU_JOB_HOURS = 24
STALE_PENDING_GPU_JOB_MESSAGE = (
    "Job GPU marcado como failed automaticamente: permaneceu pending por mais de 24h "
    "sem execução pelo worker."
)


def _as_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def fail_stale_pending_gpu_jobs(db: Session, *, now: datetime | None = None) -> int:
    """Fail GPU jobs that stayed pending past the operational timeout."""
    return fail_stale_pending_jobs(
        db,
        techniques=ML_GPU_TECHNIQUES,
        message=STALE_PENDING_GPU_JOB_MESSAGE,
        now=now,
    )


def fail_stale_pending_cpu_jobs(db: Session, *, now: datetime | None = None) -> int:
    """Fail CPU jobs that stayed pending past the operational timeout."""
    return fail_stale_pending_jobs(
        db,
        techniques=set(),  # all techniques not in ML_GPU_TECHNIQUES
        message="Job CPU marcado como failed automaticamente: permaneceu pending por mais de 24h sem execucao pelo worker.",
        now=now,
    )


def fail_stale_pending_jobs(
    db: Session,
    *,
    techniques: set[str] | frozenset[str] | None = None,
    message: str = STALE_PENDING_GPU_JOB_MESSAGE,
    now: datetime | None = None,
) -> int:
    """Fail jobs that stayed pending past the operational timeout.

    If ``techniques`` is an empty set, all techniques *not* in ML_GPU_TECHNIQUES are
    targeted. If ``techniques`` is None, all pending jobs are targeted.
    """
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(hours=STALE_PENDING_GPU_JOB_HOURS)
    query = db.query(AnalysisJob).filter(AnalysisJob.status == "pending")

    if techniques is None:
        pass
    elif len(techniques) == 0:
        query = query.filter(AnalysisJob.technique.notin_(sorted(ML_GPU_TECHNIQUES)))
    else:
        query = query.filter(AnalysisJob.technique.in_(sorted(techniques)))

    pending = query.all()
    failed = 0
    completed_at = now or datetime.now(timezone.utc)
    for job in pending:
        created_at = getattr(job, "created_at", None)
        if created_at is None or _as_aware_utc(created_at) > cutoff:
            continue
        job.status = "failed"
        job.progress = 0
        job.progress_message = message[:512]
        job.error_message = message
        job.completed_at = completed_at
        failed += 1
    if failed:
        db.commit()
    return failed


def gpu_queue_snapshot(db: Session, *, job_id: UUID | None = None) -> dict[str, Any]:
    """Return pending GPU job count and optional position for a job."""
    stale_failed = fail_stale_pending_gpu_jobs(db)
    pending = (
        db.query(AnalysisJob)
        .filter(
            AnalysisJob.status == "pending",
            AnalysisJob.technique.in_(sorted(ML_GPU_TECHNIQUES)),
        )
        .order_by(AnalysisJob.created_at.asc())
        .all()
    )
    ids = [str(j.id) for j in pending]
    out: dict[str, Any] = {
        "pending_gpu_jobs": len(pending),
        "pending_gpu_job_ids": ids,
        "stale_gpu_jobs_failed": stale_failed,
    }
    if job_id is not None:
        jid = str(job_id)
        if jid in ids:
            out["gpu_queue_position"] = ids.index(jid) + 1
        else:
            out["gpu_queue_position"] = None
    return out


def is_gpu_technique(technique: str) -> bool:
    return technique in ML_GPU_TECHNIQUES


def gpu_wait_message(snapshot: dict[str, Any]) -> str | None:
    pos = snapshot.get("gpu_queue_position")
    total = snapshot.get("pending_gpu_jobs", 0)
    if pos is None or total <= 0:
        return None
    if pos == 1 and total == 1:
        return "Aguardando worker GPU"
    return f"Aguardando GPU ({pos} de {total} na fila)"
