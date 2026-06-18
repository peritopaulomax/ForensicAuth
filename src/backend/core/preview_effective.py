"""Effective preview parameters persisted for derivative promotion."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from models.analysis_job import AnalysisJob


def merge_effective_parameters(
    job: AnalysisJob,
    job_result: dict[str, Any],
    *,
    override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge job DB parameters with persisted preview overrides and request override."""
    merged = dict(job.parameters or {})
    stored = job_result.get("effective_parameters")
    if isinstance(stored, dict):
        merged.update(stored)
    if override:
        merged.update(override)
    return merged


def load_job_result_json(result_dir: Path) -> dict[str, Any]:
    path = result_dir / "result.json"
    if not path.is_file():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def persist_effective_parameters(result_dir: Path, params: dict[str, Any]) -> dict[str, Any]:
    """Write ``effective_parameters`` into ``result.json`` and return updated payload."""
    result_path = result_dir / "result.json"
    payload = load_job_result_json(result_dir)
    payload["effective_parameters"] = dict(params)
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return payload


def sync_job_parameters(job: AnalysisJob, params: dict[str, Any]) -> None:
    """Persist effective parameters on the job row for reproducibility."""
    job.parameters = dict(params)


def sync_job_runtime_receipt(
    job: AnalysisJob,
    result_dir: Path,
    params: dict[str, Any],
) -> None:
    """Align job receipt / runtime_manifest with parameters promoted to custody."""
    payload = load_job_result_json(result_dir)
    receipt = payload.get("job_receipt")
    if isinstance(receipt, dict) and receipt.get("kind") == "job_execution_receipt":
        updated = dict(receipt)
        updated["parameters"] = dict(params)
        updated["last_promoted_at"] = datetime.now(timezone.utc).isoformat()
        payload["job_receipt"] = updated
        job.runtime_manifest = updated
        with open(result_dir / "result.json", "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        return

    manifest = job.runtime_manifest if isinstance(job.runtime_manifest, dict) else None
    if manifest and manifest.get("kind") == "job_execution_receipt":
        updated = dict(manifest)
        updated["parameters"] = dict(params)
        updated["last_promoted_at"] = datetime.now(timezone.utc).isoformat()
        job.runtime_manifest = updated


def record_promoted_derivative(
    result_dir: Path,
    *,
    evidence_id: str,
    artifact_filename: str,
    sha256: str,
    label: str | None = None,
) -> None:
    """Append promoted derivative metadata to result.json for job traceability."""
    payload = load_job_result_json(result_dir)
    promoted = payload.get("promoted_derivatives")
    if not isinstance(promoted, list):
        promoted = []
    promoted.append(
        {
            "evidence_id": evidence_id,
            "artifact_filename": artifact_filename,
            "sha256": sha256,
            "label": label,
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    payload["promoted_derivatives"] = promoted
    payload["promoted"] = True
    payload["preview"] = True
    with open(result_dir / "result.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
