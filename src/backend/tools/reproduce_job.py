#!/usr/bin/env python3
"""Re-execute a completed analysis job and compare artifact SHA-256.

Usage:
  cd src/backend
  python -m tools.reproduce_job <job-uuid>
  python -m tools.reproduce_job <job-uuid> --json

Requires DATABASE_URL and evidence files on disk (same as the API worker).
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid

from app.database import SessionLocal
from services.job_service import JobService


def _print_report(report: dict) -> None:
    status = report.get("status", "?")
    print(f"Job:       {report.get('job_id')}")
    print(f"Tecnica:   {report.get('technique')}")
    print(f"Status:    {status}")
    print(f"Perfil:    {report.get('determinism_profile')}")
    print(f"Artefato:  {report.get('primary_artifact') or '—'}")
    print()
    print(f"Original:  {report.get('original_artifact_sha256') or '—'}")
    print(f"Novo:      {report.get('reproduced_artifact_sha256') or '—'}")
    print(f"Match:     {report.get('artifact_match')}")
    print(f"Runtime:   {report.get('runtime_digest_match')}")
    orig_rt = report.get("original_runtime") or {}
    curr_rt = report.get("current_runtime") or {}
    if orig_rt.get("docker_image_digest") or curr_rt.get("docker_image_digest"):
        print()
        print(f"Digest original: {orig_rt.get('docker_image_digest') or '—'}")
        print(f"Digest atual:    {curr_rt.get('docker_image_digest') or '—'}")
    print()
    print(report.get("message", ""))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verificar reproducibilidade numerica de um job")
    parser.add_argument("job_id", help="UUID do AnalysisJob completed")
    parser.add_argument("--json", action="store_true", help="Saida JSON")
    args = parser.parse_args(argv)

    try:
        job_uuid = uuid.UUID(args.job_id)
    except ValueError:
        print(f"UUID invalido: {args.job_id}", file=sys.stderr)
        return 2

    db = SessionLocal()
    try:
        service = JobService(db)
        report = service.reproduce_job(job_uuid)
    except Exception as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_report(report)

    status = report.get("status")
    if status == "MATCH":
        return 0
    if status in ("BEST_EFFORT_MISMATCH", "NO_BASELINE"):
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
