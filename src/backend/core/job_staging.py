"""Job preview staging — single write directory per analysis job."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

_STAGING_KEY = "_job_staging_dir"


def inject_job_staging(parameters: dict[str, Any], staging_dir: Path) -> dict[str, Any]:
    """Attach per-job preview directory (results/{job_id}/)."""
    out = dict(parameters)
    out[_STAGING_KEY] = str(staging_dir.resolve())
    return out


def pop_job_staging_dir(parameters: dict[str, Any]) -> Path | None:
    raw = parameters.pop(_STAGING_KEY, None)
    if not raw:
        return None
    return Path(str(raw)).resolve()


def job_artifact_dir(parameters: dict[str, Any], *, fallback_subdir: str) -> Path:
    """Prefer injected job staging dir; otherwise legacy shared tmp folder."""
    staging = parameters.get(_STAGING_KEY)
    if staging:
        path = Path(str(staging)).resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path
    from app.config import get_settings

    path = Path(get_settings().RESULTS_DIR) / fallback_subdir
    path.mkdir(parents=True, exist_ok=True)
    return path


def job_artifact_dir_unique(
    parameters: dict[str, Any],
    *,
    fallback_subdir: str,
    evidence_path: str,
) -> Path:
    """Staging dir or legacy per-run subfolder (audio etc.)."""
    staging = parameters.get(_STAGING_KEY)
    if staging:
        path = Path(str(staging)).resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path
    stem = Path(evidence_path).stem
    from app.config import get_settings

    path = Path(get_settings().RESULTS_DIR) / fallback_subdir / f"{stem}_{uuid.uuid4().hex[:8]}"
    path.mkdir(parents=True, exist_ok=True)
    return path
