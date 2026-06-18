"""Exclusao completa de caso: remove arquivos, apaga registros operacionais, preserva cadeia de custodia."""

from __future__ import annotations

import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from models.analysis_job import AnalysisJob
from models.case import Case
from models.custody_record import CustodyRecord
from models.evidence import Evidence
from models.report import Report
from models.user import User
from services.case_access import assert_can_delete_case
from services.custody_service import CustodyService


class CaseDeletionError(Exception):
    """Erro de validacao ao excluir caso."""


def tombstone_protocol_number(original: str, case_id: uuid.UUID, *, max_length: int = 50) -> str:
    """Renomeia protocolo para liberar UNIQUE sem estourar VARCHAR(50)."""
    suffix = f"~{str(case_id).replace('-', '')[:8]}"
    if len(original) + len(suffix) <= max_length:
        return f"{original}{suffix}"
    return f"{original[: max_length - len(suffix)]}{suffix}"


class CaseDeletionService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    def delete_case(self, case_id: uuid.UUID, user: User) -> dict[str, Any]:
        case = self.db.query(Case).filter(Case.id == case_id).first()
        if not case:
            raise CaseDeletionError("Caso nao encontrado")
        if case.deleted_at is not None:
            raise CaseDeletionError("Caso ja foi excluido")

        assert_can_delete_case(case, user)

        snapshot = self._build_deletion_snapshot(case)
        files_removed = self._remove_case_files(case, snapshot)

        self._purge_operational_rows(case_id, user.id)

        original_protocol = case.protocol_number
        deleted_at = datetime.now(timezone.utc).replace(tzinfo=None)
        case.deleted_at = deleted_at
        case.deleted_by = user.id
        case.protocol_number = tombstone_protocol_number(original_protocol, case.id)
        case.status = "fechado"

        custody = CustodyService(self.db)
        custody.create_record(
            record_type="case_deleted",
            case_id=case.id,
            user_id=user.id,
            sha256_input=None,
            sha256_output=None,
            details={
                "provenance_schema_version": "1",
                "action": "case_deleted",
                "case_excluded": True,
                "deleted_at": deleted_at.isoformat(),
                "deleted_by": str(user.id),
                "original_protocol_number": original_protocol,
                "snapshot": snapshot,
                "files_removed": files_removed,
            },
            commit=False,
        )

        try:
            self.db.commit()
        except Exception as exc:
            self.db.rollback()
            raise CaseDeletionError(f"Falha ao registrar exclusao do caso: {exc}") from exc
        return {
            "case_id": str(case.id),
            "deleted": True,
            "custody_preserved": True,
            "files_removed": files_removed,
        }

    def _build_deletion_snapshot(self, case: Case) -> dict[str, Any]:
        evidences = (
            self.db.query(Evidence).filter(Evidence.case_id == case.id).all()
        )
        evidence_ids = [e.id for e in evidences]
        jobs: list[AnalysisJob] = []
        if evidence_ids:
            jobs = (
                self.db.query(AnalysisJob)
                .filter(AnalysisJob.evidence_id.in_(evidence_ids))
                .all()
            )
        reports = self.db.query(Report).filter(Report.case_id == case.id).all()

        return {
            "case_id": str(case.id),
            "protocol_number": case.protocol_number,
            "title": case.title,
            "inquiry_number": case.inquiry_number,
            "process_number": case.process_number,
            "evidence_count": len(evidences),
            "job_count": len(jobs),
            "report_count": len(reports),
            "evidences": [
                {
                    "evidence_id": str(e.id),
                    "original_filename": e.original_filename,
                    "sha256": e.sha256,
                    "file_type": e.file_type,
                    "origin": (e.extra_metadata or {}).get("origin", "upload"),
                    "was_soft_deleted": e.deleted_at is not None,
                }
                for e in evidences
            ],
            "jobs": [
                {
                    "job_id": str(j.id),
                    "evidence_id": str(j.evidence_id),
                    "technique": j.technique,
                    "status": j.status,
                    "result_sha256": j.result_sha256,
                }
                for j in jobs
            ],
            "reports": [
                {
                    "report_id": str(r.id),
                    "title": r.title,
                    "sha256": r.sha256,
                    "original_filename": Path(r.file_path).name if r.file_path else None,
                }
                for r in reports
            ],
        }

    def _remove_case_files(self, case: Case, snapshot: dict[str, Any]) -> dict[str, int]:
        counts = {"evidence_files": 0, "job_result_dirs": 0, "derivatives_dirs": 0, "report_files": 0}

        for ev in snapshot.get("evidences", []):
            ev_row = self.db.query(Evidence).filter(Evidence.id == uuid.UUID(ev["evidence_id"])).first()
            if ev_row and ev_row.file_path:
                p = Path(ev_row.file_path)
                if p.is_file():
                    p.unlink(missing_ok=True)
                    counts["evidence_files"] += 1

        for job_info in snapshot.get("jobs", []):
            job_dir = Path(self.settings.RESULTS_DIR) / job_info["job_id"]
            if job_dir.is_dir():
                shutil.rmtree(job_dir, ignore_errors=True)
                counts["job_result_dirs"] += 1
            job_row = (
                self.db.query(AnalysisJob)
                .filter(AnalysisJob.id == uuid.UUID(job_info["job_id"]))
                .first()
            )
            if job_row and job_row.result_path:
                rp = Path(job_row.result_path)
                if rp.is_file():
                    rp.unlink(missing_ok=True)
                elif rp.is_dir():
                    shutil.rmtree(rp, ignore_errors=True)

        deriv_dir = Path(self.settings.DERIVATIVES_DIR) / str(case.id)
        if deriv_dir.is_dir():
            shutil.rmtree(deriv_dir, ignore_errors=True)
            counts["derivatives_dirs"] = 1

        if getattr(case, "storage_mode", "va") == "peritus":
            from services.peritus_bridge_service import PeritusBridgeService

            PeritusBridgeService(self.db, self.settings).remove_case_storage(case.id)
            counts["peritus_storage"] = 1

        for rep in snapshot.get("reports", []):
            report = self.db.query(Report).filter(Report.id == uuid.UUID(rep["report_id"])).first()
            if report and report.file_path:
                p = Path(report.file_path)
                if p.is_file():
                    p.unlink(missing_ok=True)
                    counts["report_files"] += 1

        return counts

    def _purge_operational_rows(self, case_id: uuid.UUID, user_id: uuid.UUID) -> None:
        """Remove laudos do DB; jobs/evidencias permanecem (FK da cadeia intacta)."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        evidences = self.db.query(Evidence).filter(Evidence.case_id == case_id).all()
        evidence_ids = [e.id for e in evidences]

        if evidence_ids:
            jobs = (
                self.db.query(AnalysisJob)
                .filter(AnalysisJob.evidence_id.in_(evidence_ids))
                .all()
            )
            for job in jobs:
                # Custody records are immutable (SQLite trigger / PG policy) and keep
                # job_id references — never DELETE analysis_jobs for a purged case.
                job.status = "purged"
                job.result_path = None
                job.result_sha256 = None
                params = dict(job.parameters or {})
                params["purged_with_case"] = True
                job.parameters = params

        self.db.query(Report).filter(Report.case_id == case_id).delete(synchronize_session=False)

        for ev in evidences:
            ev.deleted_at = now
            ev.deleted_by = user_id
            meta = dict(ev.extra_metadata or {})
            meta["purged_with_case"] = True
            ev.extra_metadata = meta
            ev.file_path = ""

        self.db.flush()
