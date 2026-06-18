"""Export/import of forensic cases as Verification Case Package (VCP) ZIP archives."""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import socket
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from models.analysis_job import AnalysisJob
from models.case import Case
from models.case_closure import CaseClosure, CaseClosureSignature
from models.case_share import CaseShare
from models.custody_record import CustodyRecord
from models.evidence import Evidence
from models.report import Report
from models.user import User
from services.case_access import assert_can_create_case, get_accessible_case
from services.case_lifecycle_service import ForensicManifestBuilder
from services.custody_service import CustodyService, _allow_custody_record_updates
from services.custody_signing_service import CustodySigningService

VCP_SCHEMA_VERSION = "1"


def _canonical_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _iso_ts(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


class CaseTransferService:
    """Build, validate and ingest VCP packages."""

    def __init__(self, db: Session, settings: Settings | None = None):
        self.db = db
        self.settings = settings or get_settings()
        self.signing = CustodySigningService(self.settings)

    def export_case(
        self,
        case_id: uuid.UUID,
        current_user: User,
        output_path: Path,
    ) -> Path:
        case = get_accessible_case(self.db, case_id, current_user)

        records = (
            self.db.query(CustodyRecord)
            .filter(CustodyRecord.case_id == case_id)
            .order_by(CustodyRecord.chain_sequence.asc())
            .all()
        )
        evidence_ids_in_chain = {r.evidence_id for r in records if r.evidence_id}
        evidences = self.db.query(Evidence).filter(Evidence.case_id == case_id).all()
        if evidence_ids_in_chain:
            present = {e.id for e in evidences}
            missing = evidence_ids_in_chain - present
            if missing:
                evidences.extend(
                    self.db.query(Evidence).filter(Evidence.id.in_(missing)).all()
                )
        closures = (
            self.db.query(CaseClosure)
            .filter(CaseClosure.case_id == case_id)
            .order_by(CaseClosure.closure_sequence.asc())
            .all()
        )
        closure_sigs: list[dict] = []
        for cl in closures:
            for sig in cl.additional_signatures or []:
                closure_sigs.append(
                    {
                        "id": str(sig.id),
                        "closure_id": str(sig.closure_id),
                        "user_id": str(sig.user_id),
                        "system_signature": sig.system_signature,
                        "signed_at": _iso_ts(sig.signed_at),
                    }
                )

        user_ids: set[uuid.UUID] = {case.created_by}
        if case.assigned_to:
            user_ids.add(case.assigned_to)
        for r in records:
            user_ids.add(r.user_id)
        for e in evidences:
            user_ids.add(e.uploaded_by)
        for cl in closures:
            user_ids.add(cl.signed_by)

        job_ids = {r.job_id for r in records if r.job_id}
        jobs_payload: list[dict] = []
        if job_ids:
            jobs = self.db.query(AnalysisJob).filter(AnalysisJob.id.in_(job_ids)).all()
            for j in jobs:
                jobs_payload.append(
                    {
                        "id": str(j.id),
                        "evidence_id": str(j.evidence_id),
                        "technique": j.technique,
                        "status": j.status,
                        "parameters": j.parameters or {},
                        "result_path": j.result_path,
                        "result_sha256": j.result_sha256,
                        "artifact_sha256": j.artifact_sha256,
                        "runtime_manifest": j.runtime_manifest or {},
                        "determinism_profile": j.determinism_profile,
                        "created_by": str(j.created_by),
                        "created_at": _iso_ts(j.created_at),
                    }
                )
                user_ids.add(j.created_by)

        users = self.db.query(User).filter(User.id.in_(user_ids)).all()
        users_payload = [
            {
                "id": str(u.id),
                "username": u.username,
                "email": u.email,
                "role": u.role,
            }
            for u in users
        ]

        file_entries: dict[str, str] = {}
        tmp_files: list[Path] = []

        def register_file(path: Path, sha256: str) -> None:
            if not sha256 or sha256 in file_entries:
                return
            if path.is_file():
                file_entries[sha256] = _sha256_file(path)
            else:
                file_entries[sha256] = sha256

        for ev in evidences:
            register_file(Path(ev.file_path), ev.sha256)

        case_payload = {
            "id": str(case.id),
            "protocol_number": case.protocol_number,
            "inquiry_number": case.inquiry_number,
            "process_number": case.process_number,
            "title": case.title,
            "description": case.description,
            "status": case.status,
            "created_by": str(case.created_by),
            "assigned_to": str(case.assigned_to) if case.assigned_to else None,
            "created_at": _iso_ts(case.created_at),
            "updated_at": _iso_ts(case.updated_at),
        }

        evidences_payload = []
        for ev in evidences:
            evidences_payload.append(
                {
                    "id": str(ev.id),
                    "case_id": str(ev.case_id),
                    "filename": ev.filename,
                    "original_filename": ev.original_filename,
                    "file_size": ev.file_size,
                    "file_type": ev.file_type,
                    "mime_type": ev.mime_type,
                    "sha256": ev.sha256,
                    "extra_metadata": ev.extra_metadata or {},
                    "uploaded_by": str(ev.uploaded_by),
                    "created_at": _iso_ts(ev.created_at),
                    "storage_kind": (
                        "derivative"
                        if "derivative" in str(ev.file_path).replace("\\", "/").lower()
                        else "upload"
                    ),
                }
            )

        records_payload = []
        for rec in records:
            records_payload.append(
                {
                    "id": str(rec.id),
                    "record_type": rec.record_type,
                    "case_id": str(rec.case_id),
                    "evidence_id": str(rec.evidence_id) if rec.evidence_id else None,
                    "job_id": str(rec.job_id) if rec.job_id else None,
                    "user_id": str(rec.user_id),
                    "sha256_input": rec.sha256_input,
                    "sha256_output": rec.sha256_output,
                    "sha256_params": rec.sha256_params,
                    "details": rec.details or {},
                    "previous_record_hash": rec.previous_record_hash,
                    "record_hash": rec.record_hash,
                    "chain_sequence": rec.chain_sequence,
                    "system_signature": rec.system_signature,
                    "signing_key_id": rec.signing_key_id,
                    "timestamp": _iso_ts(rec.timestamp),
                }
            )

        closures_payload = []
        for cl in closures:
            closures_payload.append(
                {
                    "id": str(cl.id),
                    "case_id": str(cl.case_id),
                    "closure_sequence": cl.closure_sequence,
                    "manifest_sha256": cl.manifest_sha256,
                    "manifest_json": cl.manifest_json or {},
                    "signature_mode": cl.signature_mode,
                    "system_signature": cl.system_signature,
                    "signed_by": str(cl.signed_by),
                    "signed_at": _iso_ts(cl.signed_at),
                    "custody_record_id": str(cl.custody_record_id)
                    if cl.custody_record_id
                    else None,
                    "accepts_additional_signatures": cl.accepts_additional_signatures,
                }
            )

        package_meta = {
            "vcp_schema_version": VCP_SCHEMA_VERSION,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "exported_by": str(current_user.id),
            "exported_by_username": current_user.username,
            "origin": {
                "app_name": self.settings.APP_NAME,
                "app_version": self.settings.APP_VERSION,
                "hostname": socket.gethostname(),
                "docker_image": self.settings.FORENSICAUTH_IMAGE_TAG or None,
                "docker_image_digest": self.settings.FORENSICAUTH_IMAGE_DIGEST or None,
            },
            "case_id": str(case.id),
            "protocol_number": case.protocol_number,
            "file_manifest": file_entries,
        }
        package_meta["package_sha256"] = hashlib.sha256(
            _canonical_json(
                {k: v for k, v in package_meta.items() if k != "package_sha256"}
            ).encode("utf-8")
        ).hexdigest()

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("package.json", _canonical_json(package_meta))
            zf.writestr("case/case.json", _canonical_json(case_payload))
            zf.writestr("case/users.json", _canonical_json(users_payload))
            zf.writestr("case/evidences.json", _canonical_json(evidences_payload))
            zf.writestr(
                "case/custody_records.json", _canonical_json(records_payload)
            )
            if jobs_payload:
                zf.writestr("case/analysis_jobs.json", _canonical_json(jobs_payload))
            zf.writestr("case/closures.json", _canonical_json(closures_payload))
            zf.writestr(
                "case/closure_signatures.json", _canonical_json(closure_sigs)
            )
            zf.writestr("crypto/signing_key_id.txt", self.signing.key_id)
            zf.writestr("crypto/public_key.pem", self.signing.public_key_pem())

            for ev in evidences:
                src = Path(ev.file_path)
                if src.is_file():
                    zf.write(src, f"files/{ev.sha256}")

        return output_path

    def _read_package(self, zip_path: Path) -> dict[str, Any]:
        if not zip_path.is_file():
            raise HTTPException(status_code=400, detail="Arquivo VCP (Verification Case Package) invalido")
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = set(zf.namelist())

            def read_json(name: str) -> Any:
                if name not in names:
                    raise HTTPException(
                        status_code=400, detail=f"Pacote incompleto: falta {name}"
                    )
                return json.loads(zf.read(name).decode("utf-8"))

            package = read_json("package.json")
            if package.get("vcp_schema_version") != VCP_SCHEMA_VERSION:
                raise HTTPException(
                    status_code=400,
                    detail="Versao de schema VCP nao suportada",
                )

            return {
                "zip": zf,
                "package": package,
                "case": read_json("case/case.json"),
                "users": read_json("case/users.json"),
                "evidences": read_json("case/evidences.json"),
                "custody_records": read_json("case/custody_records.json"),
                "closures": read_json("case/closures.json"),
                "closure_signatures": read_json("case/closure_signatures.json"),
                "signing_key_id": zf.read("crypto/signing_key_id.txt")
                .decode("utf-8")
                .strip(),
                "public_key_pem": zf.read("crypto/public_key.pem").decode("utf-8"),
                "zip_path": zip_path,
            }

    def validate_package(self, zip_path: Path, db: Session | None = None) -> dict[str, Any]:
        """Dry-run validation without DB writes."""
        with zipfile.ZipFile(zip_path, "r") as zf:
            payload = self._load_from_zipfile(zf, zip_path)

        issues: list[str] = []
        file_report = self._validate_files(payload, issues)
        chain_report = self._validate_chain(payload, issues)
        sig_report = self._validate_signatures(payload, issues)
        closure_report = self._validate_closures(payload, issues)

        conflict_report: dict[str, Any] = {"ok": True, "conflicts": []}
        if db is not None:
            conflict_report = self._check_import_conflicts(db, payload, issues)

        valid = (
            not issues
            and file_report.get("ok", False)
            and chain_report.get("valid", False)
            and sig_report.get("ok", False)
            and closure_report.get("ok", False)
            and conflict_report.get("ok", True)
        )

        return {
            "valid": valid,
            "issues": issues,
            "package": {
                "protocol_number": payload["case"].get("protocol_number"),
                "case_id": payload["case"].get("id"),
                "exported_at": payload["package"].get("exported_at"),
                "origin": payload["package"].get("origin"),
            },
            "files": file_report,
            "chain": chain_report,
            "signatures": sig_report,
            "closures": closure_report,
            "conflicts": conflict_report,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def _load_from_zipfile(self, zf: zipfile.ZipFile, zip_path: Path) -> dict[str, Any]:
        names = set(zf.namelist())

        def read_json(name: str) -> Any:
            if name not in names:
                raise HTTPException(
                    status_code=400, detail=f"Pacote incompleto: falta {name}"
                )
            return json.loads(zf.read(name).decode("utf-8"))

        package = read_json("package.json")
        if package.get("vcp_schema_version") != VCP_SCHEMA_VERSION:
            raise HTTPException(
                status_code=400, detail="Versao de schema VCP nao suportada"
            )

        analysis_jobs: list = []
        if "case/analysis_jobs.json" in names:
            analysis_jobs = read_json("case/analysis_jobs.json")

        return {
            "package": package,
            "case": read_json("case/case.json"),
            "users": read_json("case/users.json"),
            "evidences": read_json("case/evidences.json"),
            "analysis_jobs": analysis_jobs,
            "custody_records": read_json("case/custody_records.json"),
            "closures": read_json("case/closures.json"),
            "closure_signatures": read_json("case/closure_signatures.json"),
            "signing_key_id": zf.read("crypto/signing_key_id.txt").decode("utf-8").strip(),
            "public_key_pem": zf.read("crypto/public_key.pem").decode("utf-8"),
            "zip_path": zip_path,
            "zip_names": names,
        }

    def _validate_files(self, payload: dict, issues: list[str]) -> dict[str, Any]:
        manifest = payload["package"].get("file_manifest") or {}
        missing = []
        mismatch = []
        checked = 0
        zf = zipfile.ZipFile(payload["zip_path"], "r")
        try:
            for sha256, expected in manifest.items():
                arc = f"files/{sha256}"
                if arc not in payload["zip_names"]:
                    missing.append({"sha256": sha256, "path": arc})
                    continue
                data = zf.read(arc)
                actual = hashlib.sha256(data).hexdigest()
                checked += 1
                if actual != expected or actual != sha256:
                    mismatch.append(
                        {"sha256": sha256, "expected": expected, "actual": actual}
                    )
        finally:
            zf.close()

        if missing:
            issues.append(f"{len(missing)} arquivo(s) ausente(s) no pacote")
        if mismatch:
            issues.append(f"{len(mismatch)} arquivo(s) com hash divergente")

        return {
            "ok": not missing and not mismatch,
            "checked": checked,
            "missing": missing,
            "hash_mismatch": mismatch,
        }

    def _validate_chain(self, payload: dict, issues: list[str]) -> dict[str, Any]:
        records = sorted(
            payload["custody_records"],
            key=lambda r: int(r.get("chain_sequence") or 0),
        )
        if not records:
            return {"valid": True, "records_checked": 0}

        svc = CustodyService(self.db)
        invalid = None
        for rec in records:
            obj = CustodyRecord(
                record_type=rec["record_type"],
                case_id=uuid.UUID(rec["case_id"]),
                evidence_id=uuid.UUID(rec["evidence_id"]) if rec.get("evidence_id") else None,
                job_id=uuid.UUID(rec["job_id"]) if rec.get("job_id") else None,
                user_id=uuid.UUID(rec["user_id"]),
                sha256_input=rec.get("sha256_input"),
                sha256_output=rec.get("sha256_output"),
                sha256_params=rec.get("sha256_params"),
                details=rec.get("details") or {},
                previous_record_hash=rec.get("previous_record_hash"),
                record_hash=rec["record_hash"],
                chain_sequence=int(rec.get("chain_sequence") or 0),
                timestamp=datetime.fromisoformat(
                    rec["timestamp"].replace("Z", "+00:00")
                ).replace(tzinfo=None),
            )
            if not svc._record_hash_matches(obj):
                invalid = rec.get("id")
                issues.append(f"Hash invalido no registro {invalid}")
                break

        ordered, err, orphans = svc._build_chain_ordered_list(
            [
                CustodyRecord(
                    id=uuid.UUID(r["id"]),
                    record_type=r["record_type"],
                    case_id=uuid.UUID(r["case_id"]),
                    previous_record_hash=r.get("previous_record_hash"),
                    record_hash=r["record_hash"],
                    chain_sequence=int(r.get("chain_sequence") or 0),
                    timestamp=datetime.fromisoformat(
                        r["timestamp"].replace("Z", "+00:00")
                    ).replace(tzinfo=None),
                    user_id=uuid.UUID(r["user_id"]),
                )
                for r in records
            ]
        )
        valid = invalid is None and err is None and not orphans
        if err:
            issues.append(f"Cadeia invalida: {err}")
        if orphans:
            issues.append(f"{len(orphans)} registro(s) orfao(s) na cadeia exportada")

        for idx, rec in enumerate(ordered or [], start=1):
            if int(rec.chain_sequence or 0) != idx:
                valid = False
                issues.append("Gap de chain_sequence na cadeia exportada")
                break

        return {
            "valid": valid,
            "records_checked": len(records),
            "first_invalid": invalid,
        }

    def _validate_signatures(self, payload: dict, issues: list[str]) -> dict[str, Any]:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        pub = serialization.load_pem_public_key(payload["public_key_pem"].encode())
        if not isinstance(pub, Ed25519PublicKey):
            issues.append("Chave publica invalida no pacote")
            return {"ok": False, "checked": 0, "invalid": []}

        key_id = payload["signing_key_id"]
        invalid = []
        checked = 0
        for rec in payload["custody_records"]:
            sig = rec.get("system_signature")
            if not sig:
                continue
            checked += 1
            try:
                import base64

                pub.verify(
                    base64.b64decode(sig),
                    rec["record_hash"].encode("utf-8"),
                )
                if rec.get("signing_key_id") and rec["signing_key_id"] != key_id:
                    invalid.append(rec["id"])
            except Exception:
                invalid.append(rec["id"])

        if invalid:
            issues.append(f"{len(invalid)} assinatura(s) Ed25519 invalida(s)")

        return {"ok": not invalid, "checked": checked, "invalid": invalid}

    def _validate_closures(self, payload: dict, issues: list[str]) -> dict[str, Any]:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        import base64

        pub = serialization.load_pem_public_key(payload["public_key_pem"].encode())
        builder = ForensicManifestBuilder()
        invalid = []
        for cl in payload["closures"]:
            stored = cl.get("manifest_json") or {}
            recomputed = builder.hash_manifest(
                {k: v for k, v in stored.items() if k != "manifest_sha256"}
            )
            if recomputed != cl.get("manifest_sha256"):
                invalid.append({"closure_id": cl["id"], "reason": "manifest_hash"})
                continue
            sig = cl.get("system_signature")
            if sig and isinstance(pub, Ed25519PublicKey):
                try:
                    pub.verify(
                        base64.b64decode(sig),
                        cl["manifest_sha256"].encode("utf-8"),
                    )
                except Exception:
                    invalid.append({"closure_id": cl["id"], "reason": "primary_sig"})

        for sig in payload["closure_signatures"]:
            cl = next(
                (c for c in payload["closures"] if c["id"] == sig["closure_id"]),
                None,
            )
            if not cl:
                invalid.append({"signature_id": sig["id"], "reason": "orphan_sig"})
                continue
            if isinstance(pub, Ed25519PublicKey):
                try:
                    pub.verify(
                        base64.b64decode(sig["system_signature"]),
                        cl["manifest_sha256"].encode("utf-8"),
                    )
                except Exception:
                    invalid.append({"signature_id": sig["id"], "reason": "extra_sig"})

        if invalid:
            issues.append(f"{len(invalid)} fechamento(s)/assinatura(s) invalidos")

        return {"ok": not invalid, "invalid": invalid}

    def _check_import_conflicts(
        self, db: Session, payload: dict, issues: list[str]
    ) -> dict[str, Any]:
        case_id = uuid.UUID(payload["case"]["id"])
        protocol = payload["case"]["protocol_number"]
        conflicts: list[dict[str, Any]] = []
        replaceable_tombstone: dict[str, Any] | None = None

        existing = db.query(Case).filter(Case.id == case_id).first()
        if existing:
            if existing.deleted_at is None:
                conflicts.append({"type": "case_id_exists", "case_id": str(case_id)})
            else:
                deleted_rec = (
                    db.query(CustodyRecord)
                    .filter(
                        CustodyRecord.case_id == case_id,
                        CustodyRecord.record_type == "case_deleted",
                    )
                    .order_by(CustodyRecord.chain_sequence.desc())
                    .first()
                )
                replaceable_tombstone = {
                    "case_id": str(case_id),
                    "deleted_at": _iso_ts(existing.deleted_at),
                    "tombstone_protocol_number": existing.protocol_number,
                    "deleted_by": str(existing.deleted_by) if existing.deleted_by else None,
                    "case_deleted_record_id": str(deleted_rec.id) if deleted_rec else None,
                    "case_deleted_record_hash": deleted_rec.record_hash if deleted_rec else None,
                }

        if (
            db.query(Case)
            .filter(Case.protocol_number == protocol, Case.deleted_at.is_(None))
            .first()
        ):
            conflicts.append(
                {"type": "protocol_exists", "protocol_number": protocol}
            )

        if conflicts:
            issues.append("Conflito de importacao com casos existentes")

        ok = not conflicts
        return {
            "ok": ok,
            "conflicts": conflicts,
            "replaceable_tombstone": replaceable_tombstone,
            "message": (
                "Conflito de importacao com casos existentes"
                if conflicts
                else (
                    "Substituira caso excluido (tombstone)"
                    if replaceable_tombstone
                    else None
                )
            ),
        }

    def _purge_soft_deleted_case(self, case_id: uuid.UUID) -> dict[str, Any]:
        """Remove tombstone operacional para permitir reimportacao VCP com mesmos UUIDs."""
        case = self.db.query(Case).filter(Case.id == case_id).first()
        if not case:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"message": "Caso tombstone nao encontrado", "case_id": str(case_id)},
            )
        if case.deleted_at is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"message": "Caso ainda ativo; importacao bloqueada", "case_id": str(case_id)},
            )

        custody_rows = (
            self.db.query(CustodyRecord).filter(CustodyRecord.case_id == case_id).all()
        )
        custody_count = len(custody_rows)
        job_ids_from_chain = {r.job_id for r in custody_rows if r.job_id}
        evidence_rows = self.db.query(Evidence).filter(Evidence.case_id == case_id).all()
        evidence_ids = [e.id for e in evidence_rows]

        deleted_rec = (
            self.db.query(CustodyRecord)
            .filter(
                CustodyRecord.case_id == case_id,
                CustodyRecord.record_type == "case_deleted",
            )
            .order_by(CustodyRecord.chain_sequence.desc())
            .first()
        )
        snapshot: dict[str, Any] = {
            "case_id": str(case_id),
            "deleted_at": _iso_ts(case.deleted_at),
            "tombstone_protocol_number": case.protocol_number,
            "deleted_by": str(case.deleted_by) if case.deleted_by else None,
            "custody_records_purged": custody_count,
            "evidences_purged": len(evidence_rows),
            "case_deleted_record_id": str(deleted_rec.id) if deleted_rec else None,
            "case_deleted_record_hash": deleted_rec.record_hash if deleted_rec else None,
            "purged_at": datetime.now(timezone.utc).isoformat(),
        }

        closure_ids = [
            row[0]
            for row in self.db.query(CaseClosure.id)
            .filter(CaseClosure.case_id == case_id)
            .all()
        ]
        if closure_ids:
            self.db.query(CaseClosureSignature).filter(
                CaseClosureSignature.closure_id.in_(closure_ids)
            ).delete(synchronize_session=False)
        self.db.query(CaseClosure).filter(CaseClosure.case_id == case_id).delete(
            synchronize_session=False
        )
        self.db.query(CustodyRecord).filter(CustodyRecord.case_id == case_id).delete(
            synchronize_session=False
        )
        if job_ids_from_chain:
            self.db.query(AnalysisJob).filter(
                AnalysisJob.id.in_(job_ids_from_chain)
            ).delete(synchronize_session=False)
        if evidence_ids:
            self.db.query(AnalysisJob).filter(
                AnalysisJob.evidence_id.in_(evidence_ids)
            ).delete(synchronize_session=False)
        self.db.query(Report).filter(Report.case_id == case_id).delete(
            synchronize_session=False
        )
        self.db.query(Evidence).filter(Evidence.case_id == case_id).delete(
            synchronize_session=False
        )
        self.db.query(CaseShare).filter(CaseShare.case_id == case_id).delete(
            synchronize_session=False
        )
        self.db.query(Case).filter(Case.id == case_id).delete(synchronize_session=False)
        self.db.flush()
        self.db.expire_all()
        return snapshot

    def import_case(
        self,
        zip_path: Path,
        current_user: User,
        *,
        skip_conflict_check: bool = False,
    ) -> dict[str, Any]:
        assert_can_create_case(current_user)
        report = self.validate_package(
            zip_path, db=None if skip_conflict_check else self.db
        )
        if not report["valid"]:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "message": "Verification Case Package (VCP) falhou na validacao",
                    "report": report,
                },
            )

        with zipfile.ZipFile(zip_path, "r") as zf:
            payload = self._load_from_zipfile(zf, zip_path)

        tombstone_snapshot: dict[str, Any] | None = None
        if not skip_conflict_check:
            conflicts = self._check_import_conflicts(self.db, payload, [])
            if not conflicts["ok"]:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "message": "Conflito de importacao com casos existentes",
                        **conflicts,
                    },
                )
            if conflicts.get("replaceable_tombstone"):
                tombstone_snapshot = self._purge_soft_deleted_case(
                    uuid.UUID(payload["case"]["id"])
                )

        case_data = payload["case"]
        case_id = uuid.UUID(case_data["id"])

        existing_case = self.db.query(Case).filter(Case.id == case_id).first()
        if existing_case:
            if existing_case.deleted_at is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "message": (
                            "Ja existe um caso ativo com este ID. "
                            "Exclua o caso ou importe em outra instancia."
                        ),
                        "case_id": str(case_id),
                        "protocol_number": existing_case.protocol_number,
                    },
                )
            if tombstone_snapshot is None:
                tombstone_snapshot = self._purge_soft_deleted_case(case_id)

        if self.db.query(Case).filter(Case.id == case_id).first():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": (
                        "Nao foi possivel remover o caso excluido (tombstone) "
                        "antes da importacao. Reinicie o backend e tente novamente."
                    ),
                    "case_id": str(case_id),
                },
            )

        self._ensure_stub_users(self._collect_users_for_import(payload))

        case = Case(
            id=case_id,
            protocol_number=case_data["protocol_number"],
            inquiry_number=case_data.get("inquiry_number"),
            process_number=case_data.get("process_number"),
            title=case_data["title"],
            description=case_data.get("description"),
            status=(
                "aberto"
                if case_data.get("status") in (None, "em_andamento")
                else case_data["status"]
            ),
            created_by=uuid.UUID(case_data["created_by"]),
            assigned_to=(
                uuid.UUID(case_data["assigned_to"])
                if case_data.get("assigned_to")
                else None
            ),
            created_at=datetime.fromisoformat(
                case_data["created_at"].replace("Z", "+00:00")
            ).replace(tzinfo=None),
            updated_at=datetime.fromisoformat(
                case_data["updated_at"].replace("Z", "+00:00")
            ).replace(tzinfo=None),
        )
        self.db.add(case)
        self.db.flush()

        upload_root = Path(self.settings.UPLOAD_DIR)
        deriv_root = Path(self.settings.DERIVATIVES_DIR)
        upload_root.mkdir(parents=True, exist_ok=True)
        deriv_root.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(zip_path, "r") as zf:
            for ev in payload["evidences"]:
                sha = ev["sha256"]
                arc = f"files/{sha}"
                kind = ev.get("storage_kind", "upload")
                if kind == "derivative":
                    dest_dir = deriv_root / str(case_id)
                else:
                    dest_dir = upload_root / str(case_id)
                dest_dir.mkdir(parents=True, exist_ok=True)
                dest = dest_dir / ev["filename"]
                with zf.open(arc) as src, open(dest, "wb") as out:
                    shutil.copyfileobj(src, out)

                evidence = Evidence(
                    id=uuid.UUID(ev["id"]),
                    case_id=case_id,
                    filename=ev["filename"],
                    original_filename=ev["original_filename"],
                    file_path=str(dest),
                    file_size=ev["file_size"],
                    file_type=ev["file_type"],
                    mime_type=ev.get("mime_type"),
                    sha256=ev["sha256"],
                    extra_metadata=ev.get("extra_metadata") or {},
                    uploaded_by=uuid.UUID(ev["uploaded_by"]),
                    created_at=datetime.fromisoformat(
                        ev["created_at"].replace("Z", "+00:00")
                    ).replace(tzinfo=None),
                )
                self.db.add(evidence)

        self.db.flush()

        self._ensure_stub_evidences(payload, case_id, case_data)
        self._sync_analysis_jobs_for_import(payload)

        with _allow_custody_record_updates(self.db):
            for rec in payload["custody_records"]:
                self.db.add(
                    CustodyRecord(
                        id=uuid.UUID(rec["id"]),
                        record_type=rec["record_type"],
                        case_id=case_id,
                        evidence_id=(
                            uuid.UUID(rec["evidence_id"])
                            if rec.get("evidence_id")
                            else None
                        ),
                        job_id=(
                            uuid.UUID(rec["job_id"]) if rec.get("job_id") else None
                        ),
                        user_id=uuid.UUID(rec["user_id"]),
                        sha256_input=rec.get("sha256_input"),
                        sha256_output=rec.get("sha256_output"),
                        sha256_params=rec.get("sha256_params"),
                        details=rec.get("details") or {},
                        previous_record_hash=rec.get("previous_record_hash"),
                        record_hash=rec["record_hash"],
                        chain_sequence=int(rec.get("chain_sequence") or 0),
                        system_signature=rec.get("system_signature"),
                        signing_key_id=rec.get("signing_key_id"),
                        timestamp=datetime.fromisoformat(
                            rec["timestamp"].replace("Z", "+00:00")
                        ).replace(tzinfo=None),
                    )
                )

        for cl in payload["closures"]:
            self.db.add(
                CaseClosure(
                    id=uuid.UUID(cl["id"]),
                    case_id=case_id,
                    closure_sequence=cl["closure_sequence"],
                    manifest_sha256=cl["manifest_sha256"],
                    manifest_json=cl.get("manifest_json") or {},
                    signature_mode=cl.get("signature_mode", "system"),
                    system_signature=cl.get("system_signature"),
                    signed_by=uuid.UUID(cl["signed_by"]),
                    signed_at=datetime.fromisoformat(
                        cl["signed_at"].replace("Z", "+00:00")
                    ).replace(tzinfo=None),
                    custody_record_id=(
                        uuid.UUID(cl["custody_record_id"])
                        if cl.get("custody_record_id")
                        else None
                    ),
                    accepts_additional_signatures=cl.get(
                        "accepts_additional_signatures", "false"
                    ),
                )
            )

        for sig in payload["closure_signatures"]:
            self.db.add(
                CaseClosureSignature(
                    id=uuid.UUID(sig["id"]),
                    closure_id=uuid.UUID(sig["closure_id"]),
                    user_id=uuid.UUID(sig["user_id"]),
                    system_signature=sig["system_signature"],
                    signed_at=datetime.fromisoformat(
                        sig["signed_at"].replace("Z", "+00:00")
                    ).replace(tzinfo=None),
                )
            )

        self.db.flush()

        import_meta = payload["package"].get("origin") or {}
        import_details: dict[str, Any] = {
            "imported_at": datetime.now(timezone.utc).isoformat(),
            "source_case_id": case_data["id"],
            "source_protocol": case_data["protocol_number"],
            "source_origin": import_meta,
            "package_sha256": payload["package"].get("package_sha256"),
            "records_imported": len(payload["custody_records"]),
            "evidences_imported": len(payload["evidences"]),
        }
        if tombstone_snapshot:
            import_details["replaced_tombstone"] = tombstone_snapshot
        CustodyService(self.db).create_record(
            record_type="case_imported",
            case_id=case_id,
            user_id=current_user.id,
            details=import_details,
        )

        self.db.commit()

        chain = CustodyService(self.db).verify_chain(case_id)
        return {
            "case_id": str(case_id),
            "protocol_number": case_data["protocol_number"],
            "chain_valid": chain.get("valid"),
            "records_imported": len(payload["custody_records"]),
            "evidences_imported": len(payload["evidences"]),
        }

    def _sync_analysis_jobs_for_import(self, payload: dict) -> None:
        """Insere jobs do VCP e stubs da cadeia; reutiliza linhas existentes (ex.: tombstone)."""
        seen: set[uuid.UUID] = set()

        def _remember(job_id: uuid.UUID) -> bool:
            if job_id in seen:
                return True
            seen.add(job_id)
            return False

        def _exists(job_id: uuid.UUID) -> bool:
            return (
                self.db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
                is not None
            )

        for job in payload.get("analysis_jobs") or []:
            job_id = uuid.UUID(str(job["id"]))
            if _remember(job_id) or _exists(job_id):
                continue
            created = job.get("created_at")
            self.db.add(
                AnalysisJob(
                    id=job_id,
                    evidence_id=uuid.UUID(str(job["evidence_id"])),
                    technique=str(job.get("technique") or "vcp_import")[:50],
                    status=str(job.get("status") or "purged"),
                    parameters=job.get("parameters") or {},
                    result_path=job.get("result_path"),
                    result_sha256=job.get("result_sha256"),
                    artifact_sha256=job.get("artifact_sha256"),
                    runtime_manifest=job.get("runtime_manifest") or {},
                    determinism_profile=job.get("determinism_profile"),
                    created_by=uuid.UUID(str(job["created_by"])),
                    created_at=(
                        datetime.fromisoformat(created.replace("Z", "+00:00")).replace(
                            tzinfo=None
                        )
                        if created
                        else datetime.now(timezone.utc).replace(tzinfo=None)
                    ),
                )
            )

        for rec in payload.get("custody_records") or []:
            raw_job = rec.get("job_id")
            if not raw_job:
                continue
            job_id = uuid.UUID(str(raw_job))
            if _remember(job_id) or _exists(job_id):
                continue
            raw_ev = rec.get("evidence_id")
            if not raw_ev:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={
                        "message": (
                            f"Registro de custodia {rec.get('id')} referencia job "
                            f"{job_id} sem evidence_id — pacote incompleto"
                        ),
                    },
                )
            details = rec.get("details") or {}
            technique = details.get("technique") or details.get("operation") or "vcp_import"
            if not isinstance(technique, str) or not technique.strip():
                technique = "vcp_import"
            self.db.add(
                AnalysisJob(
                    id=job_id,
                    evidence_id=uuid.UUID(str(raw_ev)),
                    technique=technique[:50],
                    status="purged",
                    parameters={"imported_vcp_stub": True},
                    created_by=uuid.UUID(str(rec["user_id"])),
                )
            )

        self.db.flush()

    def _ensure_stub_evidences(
        self, payload: dict, case_id: uuid.UUID, case_data: dict
    ) -> None:
        """Evidencias referenciadas na cadeia mas ausentes de evidences.json (ex.: soft-deleted)."""
        known = {str(e["id"]) for e in payload.get("evidences") or []}
        created_by = uuid.UUID(str(case_data["created_by"]))
        placeholder_sha = "0" * 64

        for rec in payload.get("custody_records") or []:
            raw_ev = rec.get("evidence_id")
            if not raw_ev:
                continue
            key = str(raw_ev)
            if key in known:
                continue
            ev_uuid = uuid.UUID(key)
            if self.db.query(Evidence).filter(Evidence.id == ev_uuid).first():
                known.add(key)
                continue

            details = rec.get("details") or {}
            name = (
                details.get("original_filename")
                or details.get("filename")
                or f"imported_{key[:8]}.bin"
            )
            sha = rec.get("sha256_output") or rec.get("sha256_input") or placeholder_sha
            if len(sha) != 64:
                sha = placeholder_sha
            ftype = details.get("file_type") or details.get("media") or "imagem"
            if ftype not in ("imagem", "audio", "video", "pdf"):
                ftype = "imagem"

            self.db.add(
                Evidence(
                    id=ev_uuid,
                    case_id=case_id,
                    filename=str(name)[:255],
                    original_filename=str(name)[:255],
                    file_path="",
                    file_size=0,
                    file_type=ftype,
                    mime_type=details.get("mime_type"),
                    sha256=sha,
                    extra_metadata={
                        "imported_vcp_stub": True,
                        "purged_with_case": True,
                    },
                    uploaded_by=uuid.UUID(str(rec.get("user_id", created_by))),
                    created_at=datetime.now(timezone.utc).replace(tzinfo=None),
                )
            )
            known.add(key)

        self.db.flush()

    def _collect_users_for_import(self, payload: dict) -> list[dict]:
        """Garante stubs para todos os user_id referenciados no pacote."""
        by_id: dict[str, dict] = {str(u["id"]): dict(u) for u in payload.get("users") or []}

        def ensure(uid: str | None, fallback_username: str) -> None:
            if not uid:
                return
            key = str(uid)
            if key not in by_id:
                by_id[key] = {
                    "id": key,
                    "username": fallback_username,
                    "email": f"{fallback_username}@imported.local",
                    "role": "perito",
                }

        case_data = payload.get("case") or {}
        ensure(case_data.get("created_by"), "imported_creator")
        ensure(case_data.get("assigned_to"), "imported_assignee")
        for rec in payload.get("custody_records") or []:
            ensure(rec.get("user_id"), f"imported_user_{str(rec.get('user_id', ''))[:8]}")
        for cl in payload.get("closures") or []:
            ensure(cl.get("signed_by"), f"imported_signer_{str(cl.get('signed_by', ''))[:8]}")
        for sig in payload.get("closure_signatures") or []:
            ensure(sig.get("user_id"), f"imported_sig_{str(sig.get('user_id', ''))[:8]}")
        for ev in payload.get("evidences") or []:
            ensure(ev.get("uploaded_by"), f"imported_uploader_{str(ev.get('uploaded_by', ''))[:8]}")
        for job in payload.get("analysis_jobs") or []:
            ensure(job.get("created_by"), f"imported_job_{str(job.get('created_by', ''))[:8]}")

        return list(by_id.values())

    def _ensure_stub_users(self, users: list[dict]) -> None:
        for u in users:
            uid = uuid.UUID(u["id"])
            existing = self.db.query(User).filter(User.id == uid).first()
            if existing:
                continue
            username = u["username"]
            if self.db.query(User).filter(User.username == username).first():
                username = f"{username}_imported_{str(uid)[:8]}"
            email = u.get("email") or f"{username}@imported.local"
            if self.db.query(User).filter(User.email == email).first():
                email = f"{username}+{str(uid)[:8]}@imported.local"
            self.db.add(
                User(
                    id=uid,
                    username=username,
                    email=email,
                    hashed_password="!",
                    role=u.get("role") or "perito",
                    is_active=False,
                    password_set=False,
                )
            )
        self.db.flush()
