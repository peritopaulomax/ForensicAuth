"""Full forensic integrity verification for a case."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.config import get_settings
from models.case_closure import CaseClosure, CaseClosureSignature
from models.custody_record import CustodyRecord
from models.evidence import Evidence
from services.case_lifecycle_service import ForensicManifestBuilder
from services.custody_service import CustodyService
from services.custody_signing_service import CustodySigningService


def _file_sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _canonical_details(details: Any) -> dict:
    if not details:
        return {}
    return json.loads(json.dumps(details, sort_keys=True, default=str))


class ForensicIntegrityService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()
        self.custody = CustodyService(db)
        self.signing = CustodySigningService()

    def verify_case_forensic_integrity(self, case_id: uuid.UUID) -> dict[str, Any]:
        chain_result = self.custody.verify_chain(case_id)

        records = (
            self.db.query(CustodyRecord)
            .filter(CustodyRecord.case_id == case_id)
            .order_by(CustodyRecord.chain_sequence.asc())
            .all()
        )

        invalid_sigs: List[dict] = []
        checked_sigs = 0
        for rec in records:
            if rec.system_signature:
                checked_sigs += 1
                ok = self.signing.verify_digest_hex(
                    rec.record_hash,
                    rec.system_signature,
                    rec.signing_key_id,
                )
                if not ok:
                    invalid_sigs.append(
                        {"record_id": str(rec.id), "chain_sequence": rec.chain_sequence}
                    )

        missing_files: List[dict] = []
        hash_mismatch: List[dict] = []
        files_checked = 0

        evidences = (
            self.db.query(Evidence)
            .filter(Evidence.case_id == case_id, Evidence.deleted_at.is_(None))
            .all()
        )
        for ev in evidences:
            files_checked += 1
            path = Path(ev.file_path)
            if not path.is_file():
                missing_files.append(
                    {
                        "evidence_id": str(ev.id),
                        "path": ev.file_path,
                        "original_filename": ev.original_filename,
                    }
                )
                continue
            disk_hash = _file_sha256(path)
            if disk_hash != ev.sha256:
                hash_mismatch.append(
                    {
                        "evidence_id": str(ev.id),
                        "expected": ev.sha256,
                        "actual": disk_hash,
                        "original_filename": ev.original_filename,
                    }
                )

        upload_by_evidence: dict[str, str] = {}
        for rec in records:
            if rec.record_type == "evidence_upload" and rec.evidence_id and rec.sha256_input:
                upload_by_evidence[str(rec.evidence_id)] = rec.sha256_input

        for ev in evidences:
            upload_hash = upload_by_evidence.get(str(ev.id))
            if upload_hash and upload_hash != ev.sha256:
                hash_mismatch.append(
                    {
                        "evidence_id": str(ev.id),
                        "expected": ev.sha256,
                        "actual": upload_hash,
                        "source": "custody_upload_mismatch",
                    }
                )

        provenance_issues: List[dict] = []
        evidence_sha_by_id = {str(e.id): e.sha256 for e in evidences}

        for rec in records:
            if rec.record_type != "derivative_saved":
                continue
            if rec.sha256_output:
                out_ev = next(
                    (e for e in evidences if e.sha256 == rec.sha256_output),
                    None,
                )
                if out_ev:
                    path = Path(out_ev.file_path)
                    if path.is_file():
                        disk = _file_sha256(path)
                        if disk and disk != rec.sha256_output:
                            hash_mismatch.append(
                                {
                                    "evidence_id": str(out_ev.id),
                                    "expected": rec.sha256_output,
                                    "actual": disk,
                                    "source": "derivative_saved_record",
                                }
                            )

        for ev in evidences:
            meta = ev.extra_metadata or {}
            prov = meta.get("provenance")
            if not prov:
                continue
            parents = prov.get("parent_inputs") or []
            for pin in parents:
                pid = pin.get("evidence_id")
                psha = pin.get("sha256")
                if pid and psha:
                    known = evidence_sha_by_id.get(str(pid))
                    if known and known != psha:
                        provenance_issues.append(
                            {
                                "evidence_id": str(ev.id),
                                "issue": "parent_sha_mismatch",
                                "parent_evidence_id": str(pid),
                            }
                        )
            out = prov.get("output") or {}
            if out.get("sha256") and out.get("sha256") != ev.sha256:
                provenance_issues.append(
                    {
                        "evidence_id": str(ev.id),
                        "issue": "output_sha_mismatch",
                    }
                )

            for rec in records:
                if rec.record_type != "derivative_saved":
                    continue
                if rec.sha256_output != ev.sha256:
                    continue
                rec_prov = (rec.details or {}).get("provenance")
                if rec_prov:
                    if _canonical_details(rec_prov) != _canonical_details(prov):
                        provenance_issues.append(
                            {
                                "evidence_id": str(ev.id),
                                "issue": "custody_provenance_drift",
                                "record_id": str(rec.id),
                            }
                        )

        closure_results: List[dict] = []
        closures = (
            self.db.query(CaseClosure)
            .filter(CaseClosure.case_id == case_id)
            .order_by(CaseClosure.closure_sequence.asc())
            .all()
        )
        builder = ForensicManifestBuilder()
        for cl in closures:
            stored = cl.manifest_json or {}
            recomputed = builder.hash_manifest(
                {k: v for k, v in stored.items() if k != "manifest_sha256"}
            ) if stored else ""
            manifest_valid = recomputed == cl.manifest_sha256
            sig_valid = self.signing.verify_digest_hex(
                cl.manifest_sha256,
                cl.system_signature,
            )
            extra_invalid = []
            for add in cl.additional_signatures or []:
                if not self.signing.verify_digest_hex(
                    cl.manifest_sha256, add.system_signature
                ):
                    extra_invalid.append(str(add.id))
            closure_results.append(
                {
                    "closure_sequence": cl.closure_sequence,
                    "closure_id": str(cl.id),
                    "manifest_valid": manifest_valid,
                    "primary_signature_valid": sig_valid,
                    "additional_invalid": extra_invalid,
                    "signatures_valid": sig_valid and not extra_invalid,
                }
            )

        warnings: List[str] = []
        if checked_sigs < len(records):
            warnings.append(
                f"{len(records) - checked_sigs} registro(s) historico(s) sem assinatura Ed25519"
            )

        valid = (
            chain_result.get("valid", False)
            and not invalid_sigs
            and not missing_files
            and not hash_mismatch
            and not provenance_issues
            and all(c.get("signatures_valid", True) for c in closure_results)
            and all(c.get("manifest_valid", True) for c in closure_results)
        )

        return {
            "valid": valid,
            "chain": chain_result,
            "signatures": {
                "checked": checked_sigs,
                "invalid": invalid_sigs,
            },
            "files": {
                "checked": files_checked,
                "missing": missing_files,
                "hash_mismatch": hash_mismatch,
            },
            "provenance": {"issues": provenance_issues},
            "closures": closure_results,
            "warnings": warnings,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
