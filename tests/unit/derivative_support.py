"""Shared helpers for derivative promote/save tests."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from services.job_service import build_job_result_dir  # re-export convenience

__all__ = ["seed_job_preview", "build_job_result_dir"]


def seed_job_preview(
    *,
    job_id: uuid.UUID,
    result_dir: Path,
    technique: str,
    parameters: dict[str, Any],
    extra_result: dict[str, Any] | None = None,
    evidence_sha256: str | None = None,
) -> dict[str, Any]:
    """Write result.json with job_execution_receipt (preview-tier promote flow)."""
    from app.config import get_settings
    from core.reproducibility import build_job_execution_receipt, build_runtime_manifest

    settings = get_settings()
    result: dict[str, Any] = {
        "success": True,
        "adapter": technique,
        "status": "completed",
        "preview": True,
        "promoted": False,
        **(extra_result or {}),
    }
    runtime = build_runtime_manifest(
        app_version=settings.APP_VERSION,
        gpu_available=settings.GPU_AVAILABLE,
        models_dir=settings.MODELS_DIR,
        technique=technique,
    )
    receipt = build_job_execution_receipt(
        technique=technique,
        result=result,
        runtime_manifest=runtime,
        job_id=str(job_id),
        parameters=parameters,
        input_evidence_sha256=evidence_sha256,
    )
    result["job_receipt"] = receipt
    (result_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return receipt
