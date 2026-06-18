"""GPU job queue visibility for pending ML jobs."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from core.gpu_inference import ML_GPU_TECHNIQUES
from models.analysis_job import AnalysisJob


def gpu_queue_snapshot(db: Session, *, job_id: UUID | None = None) -> dict[str, Any]:
    """Return pending GPU job count and optional position for a job."""
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
