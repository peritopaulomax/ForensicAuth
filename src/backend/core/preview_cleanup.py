"""Cleanup expired job preview directories.

Canonical layout: ``RESULTS_DIR/{case_id}/{evidence_id}/{job_id}/``
Legacy layout (still removed when found): ``RESULTS_DIR/{job_id}/``
Shared technique fallbacks (``ela/``, ``*_tmp/``, …) are also disposable.

Everything under ``RESULTS_DIR`` is preview/cache. Derivatives live under
``DERIVATIVES_DIR`` with custody and are never touched here.
"""

from __future__ import annotations

import json
import logging
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.config import get_settings
from models.analysis_job import AnalysisJob
from sqlalchemy.orm import Session, joinedload

logger = logging.getLogger(__name__)

# When retention_days=0, keep a short grace window so in-flight jobs are not wiped.
_IMMEDIATE_GRACE = timedelta(hours=1)


def _parse_completed_at(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _retention_cutoff(retention_days: int) -> datetime:
    now = datetime.now(timezone.utc)
    if retention_days > 0:
        return now - timedelta(days=retention_days)
    return now - _IMMEDIATE_GRACE


def _is_disposable_result_payload(payload: dict | None) -> bool:
    """RESULTS_DIR content is disposable; legacy JSON may omit ``preview``."""
    if payload is None:
        return True
    if "preview" not in payload:
        return True
    return bool(payload.get("preview"))


def _load_result_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def _mtime_utc(path: Path) -> datetime | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    except OSError:
        return None


def _dir_newest_mtime(path: Path) -> datetime | None:
    newest: datetime | None = _mtime_utc(path)
    try:
        for child in path.rglob("*"):
            stamp = _mtime_utc(child)
            if stamp is None:
                continue
            if newest is None or stamp > newest:
                newest = stamp
    except OSError:
        pass
    return newest


def _prune_empty_parents(removed_dir: Path, stop_at: Path) -> None:
    """Remove empty evidence/case parents after a job preview dir is deleted."""
    try:
        stop = stop_at.resolve()
        parent = removed_dir.parent.resolve()
    except OSError:
        return
    while parent != stop and stop in parent.parents:
        try:
            if any(parent.iterdir()):
                break
            parent.rmdir()
        except OSError:
            break
        parent = parent.parent


def _remove_preview_directory(target: Path, results_root: Path) -> bool:
    if not target.is_dir():
        return False
    try:
        resolved = target.resolve()
        root = results_root.resolve()
    except OSError:
        return False
    if resolved == root or root not in resolved.parents:
        return False
    shutil.rmtree(resolved, ignore_errors=True)
    if resolved.exists():
        return False
    logger.info("Preview removido: %s", resolved)
    _prune_empty_parents(resolved, root)
    return True


def _iter_result_json_job_dirs(results_root: Path) -> list[Path]:
    if not results_root.is_dir():
        return []
    found: list[Path] = []
    for result_json in results_root.rglob("result.json"):
        if not result_json.is_file():
            continue
        job_dir = result_json.parent
        if job_dir.resolve() == results_root.resolve():
            continue
        found.append(job_dir)
    return found


def _resolve_job_preview_dir(job: AnalysisJob, results_root: Path) -> Path | None:
    """Prefer result_path, then canonical nested path, then legacy flat path."""
    if job.result_path:
        candidate = Path(str(job.result_path))
        if candidate.is_dir():
            return candidate

    evidence = getattr(job, "evidence", None)
    case_id = getattr(evidence, "case_id", None) if evidence is not None else None
    if case_id is not None and job.evidence_id is not None:
        from services.job_service import build_job_result_dir

        nested = build_job_result_dir(results_root, case_id, job.evidence_id, job.id)
        if nested.is_dir():
            return nested

    legacy = results_root / str(job.id)
    if legacy.is_dir():
        return legacy
    return None


def _cleanup_orphan_top_level(results_root: Path, cutoff: datetime, removed: set[Path]) -> int:
    """Remove expired technique fallbacks / UUID orphans without (or outside) result.json trees."""
    count = 0
    if not results_root.is_dir():
        return 0
    for child in list(results_root.iterdir()):
        if not child.is_dir():
            # stray files under RESULTS_DIR are also disposable
            stamp = _mtime_utc(child)
            if stamp is not None and stamp <= cutoff:
                try:
                    child.unlink(missing_ok=True)
                    count += 1
                    logger.info("Arquivo residual de preview removido: %s", child)
                except OSError:
                    pass
            continue
        try:
            resolved = child.resolve()
        except OSError:
            continue
        if resolved in removed:
            continue
        # Nested case trees: if this UUID dir still has nested result.json, handled elsewhere.
        if any(child.rglob("result.json")):
            # May still be empty after nested job removal; prune if empty/expired leftovers.
            stamp = _dir_newest_mtime(child)
            if stamp is None or stamp > cutoff:
                continue
            # Has result.json younger handled by other loop; if all expired leftover, remove whole tree.
            # Only remove if EVERY result.json is disposable+expired (already processed) or corrupt.
            still_fresh = False
            for rj in child.rglob("result.json"):
                payload = _load_result_json(rj)
                rj_stamp = _mtime_utc(rj)
                if not _is_disposable_result_payload(payload):
                    still_fresh = True
                    break
                if rj_stamp is not None and rj_stamp > cutoff:
                    still_fresh = True
                    break
            if still_fresh:
                continue
            if _remove_preview_directory(child, results_root):
                removed.add(resolved)
                count += 1
            continue

        stamp = _dir_newest_mtime(child)
        if stamp is None or stamp > cutoff:
            continue
        if _remove_preview_directory(child, results_root):
            removed.add(resolved)
            count += 1
    return count


def cleanup_expired_job_previews(db: Session | None = None) -> int:
    """Delete expired preview folders under RESULTS_DIR.

    Uses the database when provided (preferred). Always also sweeps the filesystem
    for orphaned preview dirs (nested, legacy UUID, technique ``*_tmp`` fallbacks).
    """
    settings = get_settings()
    retention_days = int(getattr(settings, "JOB_PREVIEW_RETENTION_DAYS", 0))
    cutoff = _retention_cutoff(retention_days)
    results_root = Path(settings.RESULTS_DIR).resolve()
    removed_paths: set[Path] = set()
    removed_count = 0

    if db is not None:
        jobs = (
            db.query(AnalysisJob)
            .options(joinedload(AnalysisJob.evidence))
            .filter(AnalysisJob.status == "completed", AnalysisJob.completed_at.isnot(None))
            .all()
        )
        for job in jobs:
            completed = _parse_completed_at(job.completed_at)
            if completed is None or completed > cutoff:
                continue
            target = _resolve_job_preview_dir(job, results_root)
            if target is None:
                continue
            result_json = target / "result.json"
            if result_json.is_file():
                payload = _load_result_json(result_json)
                if not _is_disposable_result_payload(payload):
                    continue
            if _remove_preview_directory(target, results_root):
                try:
                    removed_paths.add(target.resolve())
                except OSError:
                    removed_paths.add(target)
                removed_count += 1

    for job_dir in _iter_result_json_job_dirs(results_root):
        try:
            resolved = job_dir.resolve()
        except OSError:
            continue
        if resolved in removed_paths:
            continue
        result_json = job_dir / "result.json"
        payload = _load_result_json(result_json)
        if not _is_disposable_result_payload(payload):
            continue
        stamp = _mtime_utc(result_json) or _dir_newest_mtime(job_dir)
        if stamp is None or stamp > cutoff:
            continue
        if _remove_preview_directory(job_dir, results_root):
            removed_paths.add(resolved)
            removed_count += 1

    removed_count += _cleanup_orphan_top_level(results_root, cutoff, removed_paths)
    return removed_count


def remove_job_preview_by_id(job_id: uuid.UUID | str, db: Session | None = None) -> bool:
    """Force-remove a single job preview directory (tests / admin)."""
    settings = get_settings()
    results_root = Path(settings.RESULTS_DIR).resolve()
    if db is not None:
        job = (
            db.query(AnalysisJob)
            .options(joinedload(AnalysisJob.evidence))
            .filter(AnalysisJob.id == job_id)
            .first()
        )
        if job is not None:
            target = _resolve_job_preview_dir(job, results_root)
            if target is not None:
                return _remove_preview_directory(target, results_root)
    legacy = results_root / str(job_id)
    return _remove_preview_directory(legacy, results_root)


def purge_all_previews() -> int:
    """Delete every top-level entry under RESULTS_DIR (operator/emergency wipe)."""
    settings = get_settings()
    results_root = Path(settings.RESULTS_DIR).resolve()
    if not results_root.is_dir():
        return 0
    removed = 0
    for child in list(results_root.iterdir()):
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
            if not child.exists():
                removed += 1
        else:
            try:
                child.unlink(missing_ok=True)
                removed += 1
            except OSError:
                pass
    logger.info("Purge total de RESULTS_DIR: %s entradas removidas (%s)", removed, results_root)
    return removed
