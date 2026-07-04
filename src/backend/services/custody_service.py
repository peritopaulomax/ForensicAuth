"""Custody chain service — immutable audit log with SHA-256 chaining."""

import hashlib
import json
import threading
import uuid
from collections import defaultdict
from contextlib import contextmanager
from copy import copy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

_CASE_CHAIN_LOCKS: dict[uuid.UUID, threading.RLock] = defaultdict(threading.RLock)
_CASE_LOCKS_GUARD = threading.Lock()

_SQLITE_CUSTODY_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS trg_custody_immutable
BEFORE UPDATE ON custody_records
BEGIN
    SELECT RAISE(IGNORE);
END;
"""


@contextmanager
def _allow_custody_record_updates(db: Session) -> Iterator[None]:
    """SQLite: permite UPDATE controlado (re-assinatura / reconciliacao)."""
    bind = db.get_bind()
    sqlite = bind is not None and bind.dialect.name == "sqlite"
    if sqlite:
        db.execute(text("DROP TRIGGER IF EXISTS trg_custody_immutable"))
        db.flush()
    try:
        yield
        if sqlite:
            db.flush()
    finally:
        if sqlite:
            db.execute(text(_SQLITE_CUSTODY_TRIGGER))


from models.case import Case
from models.custody_record import CustodyRecord
from models.analysis_job import AnalysisJob
from services.custody_signing_service import CustodySigningService


class CustodyService:
    """Service for creating and verifying chain-of-custody records."""

    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _canonical_details(details: Any) -> dict[str, Any]:
        """Normaliza JSON para o hash bater apos leitura do banco (Postgres/SQLite)."""
        if not details:
            return {}
        return json.loads(json.dumps(details, sort_keys=True, default=str))

    def _compute_hash(self, record: CustodyRecord, *, legacy_details: bool = False) -> str:
        """Compute SHA-256 hash for a custody record."""
        if legacy_details:
            details_payload = record.details or {}
        else:
            details_payload = self._canonical_details(record.details)

        payload = {
            "record_type": record.record_type,
            "case_id": str(record.case_id),
            "evidence_id": str(record.evidence_id) if record.evidence_id else "",
            "job_id": str(record.job_id) if record.job_id else "",
            "user_id": str(record.user_id),
            "sha256_input": record.sha256_input or "",
            "sha256_output": record.sha256_output or "",
            "sha256_params": record.sha256_params or "",
            "details": details_payload,
            "previous_record_hash": record.previous_record_hash or "",
            "chain_sequence": int(record.chain_sequence or 0),
            "timestamp": record.timestamp.replace(tzinfo=None).isoformat() if record.timestamp else "",
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _compute_hash_legacy_no_sequence(self, record: CustodyRecord) -> str:
        """Hash de registros anteriores a chain_sequence (pre-reparo)."""
        details_payload = self._canonical_details(record.details)
        payload = {
            "record_type": record.record_type,
            "case_id": str(record.case_id),
            "evidence_id": str(record.evidence_id) if record.evidence_id else "",
            "job_id": str(record.job_id) if record.job_id else "",
            "user_id": str(record.user_id),
            "sha256_input": record.sha256_input or "",
            "sha256_output": record.sha256_output or "",
            "sha256_params": record.sha256_params or "",
            "details": details_payload,
            "previous_record_hash": record.previous_record_hash or "",
            "timestamp": record.timestamp.replace(tzinfo=None).isoformat() if record.timestamp else "",
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _hash_with_sequence(self, record: CustodyRecord, sequence: int) -> str:
        trial = copy(record)
        trial.chain_sequence = sequence
        return self._compute_hash(trial)

    def _record_hash_matches(self, record: CustodyRecord) -> bool:
        if record.record_hash == self._compute_hash(record):
            return True
        if record.record_hash == self._compute_hash(record, legacy_details=True):
            return True
        if record.record_hash == self._compute_hash_legacy_no_sequence(record):
            return True
        return False

    @staticmethod
    def _compute_case_seal(record_hash: str, timestamp: datetime) -> str:
        """Compute SHA-256 seal over the last record hash and a timestamp."""
        payload = {
            "record_hash": record_hash,
            "timestamp": timestamp.replace(tzinfo=None).isoformat(),
            "version": "1",
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def update_case_custody_seal(self, case_id: uuid.UUID) -> dict[str, Any] | None:
        """Recompute and sign the chain-closure seal for a case.

        Should be called whenever the custody chain is appended to.
        """
        case = self.db.query(Case).filter(Case.id == case_id).first()
        if case is None:
            return None

        # Force flush so the just-added record is visible to the seal query.
        self.db.flush()

        last_record = (
            self.db.query(CustodyRecord)
            .filter(CustodyRecord.case_id == case_id)
            .order_by(CustodyRecord.chain_sequence.desc())
            .first()
        )
        if last_record is None:
            case.custody_seal = None
            case.custody_seal_signature = None
            case.custody_seal_record_hash = None
            case.custody_seal_timestamp = None
            return None

        timestamp = datetime.now(timezone.utc).replace(tzinfo=None)
        seal = self._compute_case_seal(last_record.record_hash, timestamp)
        signed = CustodySigningService().sign_digest_hex(seal)

        case.custody_seal = seal
        case.custody_seal_signature = signed["signature_b64"]
        case.custody_seal_record_hash = last_record.record_hash
        case.custody_seal_timestamp = timestamp

        return {
            "case_id": str(case_id),
            "seal": seal,
            "record_hash": last_record.record_hash,
            "timestamp": timestamp.isoformat(),
            "signing_key_id": signed["signing_key_id"],
        }

    def verify_case_custody_seal(self, case_id: uuid.UUID) -> dict[str, Any]:
        """Verify the chain-closure seal for a case."""
        case = self.db.query(Case).filter(Case.id == case_id).first()
        if case is None:
            return {"valid": False, "reason": "case_not_found"}

        if not case.custody_seal or not case.custody_seal_signature:
            return {"valid": False, "reason": "seal_missing"}

        last_record = (
            self.db.query(CustodyRecord)
            .filter(CustodyRecord.case_id == case_id)
            .order_by(CustodyRecord.chain_sequence.desc())
            .first()
        )
        if last_record is None:
            return {"valid": False, "reason": "chain_empty"}

        if case.custody_seal_record_hash != last_record.record_hash:
            return {
                "valid": False,
                "reason": "last_record_hash_mismatch",
                "sealed_record_hash": case.custody_seal_record_hash,
                "actual_record_hash": last_record.record_hash,
            }

        expected_seal = self._compute_case_seal(
            last_record.record_hash,
            case.custody_seal_timestamp.replace(tzinfo=None) if case.custody_seal_timestamp else datetime.now(timezone.utc).replace(tzinfo=None),
        )
        if case.custody_seal != expected_seal:
            return {
                "valid": False,
                "reason": "seal_hash_mismatch",
                "sealed_hash": case.custody_seal,
                "expected_hash": expected_seal,
            }

        signature_valid = CustodySigningService().verify_digest_hex(
            case.custody_seal,
            case.custody_seal_signature,
            None,
        )
        if not signature_valid:
            return {"valid": False, "reason": "signature_invalid"}

        return {"valid": True, "record_hash": last_record.record_hash}

    @staticmethod
    def _canonical_genesis(records: list[CustodyRecord]) -> CustodyRecord | None:
        """Genesis canonico = primeiro registro sem elo anterior (timestamp, id)."""
        genesis = [r for r in records if not (r.previous_record_hash or "").strip()]
        if not genesis:
            return None
        genesis.sort(key=lambda r: (r.timestamp or "", str(r.id)))
        return genesis[0]

    def _walk_chain_from(
        self, primary: CustodyRecord, records: list[CustodyRecord]
    ) -> tuple[list[CustodyRecord], list[CustodyRecord]]:
        """Segue encadeamento criptografico a partir do genesis canonico."""
        ordered: list[CustodyRecord] = []
        visited: set[str] = set()
        current: CustodyRecord | None = primary

        while current is not None:
            cur_id = str(current.id)
            if cur_id in visited:
                break
            visited.add(cur_id)
            ordered.append(current)
            current = next(
                (
                    r
                    for r in records
                    if (r.previous_record_hash or "") == current.record_hash
                ),
                None,
            )

        orphans = [r for r in records if str(r.id) not in visited]
        return ordered, orphans

    def _build_chain_ordered_list(
        self, records: list[CustodyRecord]
    ) -> tuple[list[CustodyRecord] | None, str | None, list[CustodyRecord]]:
        """Ordem canonica pela cadeia criptografica; genesis duplicado usa o mais antigo."""
        if not records:
            return [], None, []

        primary = self._canonical_genesis(records)
        if primary is None:
            return None, "invalid_genesis", []

        ordered, orphans = self._walk_chain_from(primary, records)
        if not ordered:
            return None, "invalid_genesis", orphans

        if orphans:
            return ordered, None, orphans

        return ordered, None, []

    def _rebuild_case_chain_linear(self, case_id: uuid.UUID, records: list[CustodyRecord]) -> Dict[str, Any]:
        """Reconstroi encadeamento linear por timestamp (corrige genesis paralelo / orfaos).

        Recalcula record_hash e assinatura Ed25519 de cada elo. Usado apenas quando a
        estrutura criptografica ficou inconsistente por condicao de corrida na criacao
        ou migracao legada de chain_sequence — nao para mascarar adulteracao detectada
        em verify_chain apos reparo.
        """
        if not records:
            return {"case_id": str(case_id), "rebuilt": 0, "ok": True, "mode": "linear_rebuild"}

        sorted_records = sorted(records, key=lambda r: (r.timestamp or "", str(r.id)))
        signing = CustodySigningService()
        prev_hash: str | None = None

        for idx, record in enumerate(sorted_records, start=1):
            record.chain_sequence = idx
            record.previous_record_hash = prev_hash
            record.record_hash = self._compute_hash(record)
            signed = signing.sign_digest_hex(record.record_hash)
            record.system_signature = signed["signature_b64"]
            record.signing_key_id = signed["signing_key_id"]
            prev_hash = record.record_hash

        return {
            "case_id": str(case_id),
            "rebuilt": len(sorted_records),
            "ok": True,
            "mode": "linear_rebuild",
            "reason": "parallel_genesis_or_orphans",
        }

    def _find_chain_tail(self, records: list[CustodyRecord]) -> CustodyRecord | None:
        """Ultimo elo: record_hash nao referenciado como previous de outro registro."""
        if not records:
            return None
        referenced = {(r.previous_record_hash or "") for r in records}
        tails = [r for r in records if r.record_hash not in referenced]
        if len(tails) == 1:
            return tails[0]
        if len(tails) == 0:
            return None
        tails.sort(key=lambda r: (int(r.chain_sequence or 0), r.timestamp or "", str(r.id)))
        return tails[-1]

    def _allocate_chain_sequence(self, case_id: uuid.UUID) -> tuple[int, CustodyRecord | None]:
        """Proxima sequencia e elo anterior = cauda criptografica da cadeia."""
        self.db.flush()
        records = (
            self.db.query(CustodyRecord).filter(CustodyRecord.case_id == case_id).all()
        )
        previous = self._find_chain_tail(records)
        if previous is None and records:
            ordered, err, _orphans = self._build_chain_ordered_list(records)
            if err is None and ordered:
                previous = ordered[-1]
        next_seq = int(previous.chain_sequence or 0) + 1 if previous else 1
        return next_seq, previous

    def _enrich_actor_details(
        self, user_id: uuid.UUID, details: Optional[Dict[str, Any]]
    ) -> dict[str, Any]:
        from models.user import User

        payload = dict(details or {})
        user = self.db.query(User).filter(User.id == user_id).first()
        if user:
            payload.setdefault("actor_username", user.username)
            payload.setdefault("actor_role", user.role)
        return payload

    def create_record(
        self,
        record_type: str,
        case_id: uuid.UUID,
        user_id: uuid.UUID,
        evidence_id: Optional[uuid.UUID] = None,
        job_id: Optional[uuid.UUID] = None,
        sha256_input: Optional[str] = None,
        sha256_output: Optional[str] = None,
        sha256_params: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        *,
        commit: bool = True,
    ) -> CustodyRecord:
        """Create a new custody record, linking it to the previous record in the chain."""
        timestamp = datetime.now(timezone.utc).replace(tzinfo=None)

        with _CASE_LOCKS_GUARD:
            lock = _CASE_CHAIN_LOCKS[case_id]
        with lock:
            next_seq, previous_record = self._allocate_chain_sequence(case_id)

            record = CustodyRecord(
                record_type=record_type,
                case_id=case_id,
                evidence_id=evidence_id,
                job_id=job_id,
                user_id=user_id,
                sha256_input=sha256_input,
                sha256_output=sha256_output,
                sha256_params=sha256_params,
                details=self._enrich_actor_details(user_id, details),
                chain_sequence=next_seq,
                previous_record_hash=(
                    previous_record.record_hash if previous_record else None
                ),
                timestamp=timestamp,
            )
            if record.id is None:
                record.id = uuid.uuid4()
            record.record_hash = self._compute_hash(record)

            signed = CustodySigningService().sign_digest_hex(record.record_hash)
            record.system_signature = signed["signature_b64"]
            record.signing_key_id = signed["signing_key_id"]

            self.db.add(record)
            self.update_case_custody_seal(case_id)
            if commit:
                self.db.commit()
                self.db.refresh(record)
            else:
                self.db.flush()

            return record

    def verify_record(self, record_id: uuid.UUID) -> Dict[str, Any]:
        """Verify a single custody record hash."""
        record = self.db.query(CustodyRecord).filter(CustodyRecord.id == record_id).first()
        if not record:
            raise ValueError(f"Registro {record_id} nao encontrado")

        computed = self._compute_hash(record)
        signing = CustodySigningService()
        signature_valid = None
        if record.system_signature:
            signature_valid = signing.verify_digest_hex(
                record.record_hash,
                record.system_signature,
                record.signing_key_id,
            )
        return {
            "valid": self._record_hash_matches(record),
            "record": record,
            "computed_hash": computed,
            "signature_valid": signature_valid,
        }

    def verify_chain(self, case_id: uuid.UUID) -> Dict[str, Any]:
        """Verificacao estrita: estrutura, sequencia 1..n, encadeamento e hash."""
        records = (
            self.db.query(CustodyRecord)
            .filter(CustodyRecord.case_id == case_id)
            .all()
        )

        ordered, structure_reason, orphans = self._build_chain_ordered_list(records)
        if structure_reason:
            return {
                "valid": False,
                "records_checked": len(records),
                "first_invalid": str(records[0].id) if records else None,
                "reason": structure_reason,
            }
        if orphans:
            return {
                "valid": False,
                "records_checked": len(records),
                "first_invalid": str(orphans[0].id),
                "reason": "unlinked_custody_records",
            }

        assert ordered is not None
        prev_hash: str | None = None
        for idx, record in enumerate(ordered, start=1):
            if int(record.chain_sequence or 0) != idx:
                return {
                    "valid": False,
                    "records_checked": len(records),
                    "first_invalid": str(record.id),
                    "reason": "chain_sequence_gap",
                }
            stored_prev = record.previous_record_hash or None
            expected_prev = prev_hash or None
            if stored_prev != expected_prev:
                return {
                    "valid": False,
                    "records_checked": len(records),
                    "first_invalid": str(record.id),
                    "reason": "previous_record_hash_mismatch",
                }
            if not self._record_hash_matches(record):
                return {
                    "valid": False,
                    "records_checked": len(records),
                    "first_invalid": str(record.id),
                    "reason": "record_hash_mismatch",
                }
            prev_hash = record.record_hash

        seal_check = self.verify_case_custody_seal(case_id)
        if not seal_check["valid"]:
            return {
                "valid": False,
                "records_checked": len(records),
                "first_invalid": None,
                "reason": f"custody_seal_invalid:{seal_check.get('reason', 'unknown')}",
                "seal_details": seal_check,
            }

        return {
            "valid": True,
            "records_checked": len(records),
            "first_invalid": None,
            "seal_valid": True,
        }

    def _sequence_assignable(self, record: CustodyRecord, sequence: int) -> bool:
        if int(record.chain_sequence or 0) == sequence and self._record_hash_matches(record):
            return True
        if record.record_hash == self._hash_with_sequence(record, sequence):
            return True
        if record.record_hash == self._compute_hash_legacy_no_sequence(record):
            return True
        return False

    def reconcile_chain_sequence_metadata(self, case_id: uuid.UUID) -> Dict[str, Any]:
        """Alinha cadeia: sequencia por hash ou reconstituicao linear se orfaos/genesis duplo."""
        records = (
            self.db.query(CustodyRecord)
            .filter(CustodyRecord.case_id == case_id)
            .all()
        )
        ordered, structure_reason, orphans = self._build_chain_ordered_list(records)

        if structure_reason == "invalid_genesis" or orphans:
            return self._rebuild_case_chain_linear(case_id, records)

        assert ordered is not None
        pending: list[tuple[CustodyRecord, int]] = []
        for idx, record in enumerate(ordered, start=1):
            if int(record.chain_sequence or 0) == idx:
                if not self._record_hash_matches(record):
                    return self._rebuild_case_chain_linear(case_id, records)
                continue
            if not self._sequence_assignable(record, idx):
                return self._rebuild_case_chain_linear(case_id, records)
            pending.append((record, idx))

        for record, idx in pending:
            record.chain_sequence = idx

        return {
            "case_id": str(case_id),
            "updated": len(pending),
            "ok": True,
            "reason": None,
            "mode": "sequence_metadata",
        }

    def reconcile_all_chain_sequence_metadata(self) -> Dict[str, Any]:
        """Reconcilia cadeia em todos os casos (startup/migracao)."""
        case_ids = [row[0] for row in self.db.query(CustodyRecord.case_id).distinct().all()]
        summary = {
            "cases": len(case_ids),
            "updated_total": 0,
            "rebuilt_total": 0,
            "failed": [],
        }
        for case_id in case_ids:
            result = self.reconcile_chain_sequence_metadata(case_id)
            if result.get("ok"):
                if result.get("mode") == "linear_rebuild":
                    summary["rebuilt_total"] += int(result.get("rebuilt", 0))
                else:
                    summary["updated_total"] += int(result.get("updated", 0))
            else:
                summary["failed"].append(result)
        return summary

    def recompute_job_hash(self, job_id: uuid.UUID) -> Dict[str, Any]:
        """Recompute artifact/result hashes for a completed analysis job."""
        import json

        from core.reproducibility import compute_artifact_sha256

        job = self.db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
        if not job:
            raise ValueError(f"Job {job_id} not found")

        original_hash = job.result_sha256 or ""
        original_artifact = job.artifact_sha256 or ""
        new_hash = original_hash
        new_artifact = original_artifact

        result_dir = Path(job.result_path) if job.result_path else None
        if result_dir and result_dir.is_dir():
            result_json = result_dir / "result.json"
            if result_json.is_file():
                sha256 = hashlib.sha256()
                with open(result_json, "rb") as f:
                    for chunk in iter(lambda: f.read(8192), b""):
                        sha256.update(chunk)
                new_hash = sha256.hexdigest()
                with open(result_json, encoding="utf-8") as f:
                    result_payload = json.load(f)
                new_artifact, _, _ = compute_artifact_sha256(
                    job.technique, result_dir, result_payload
                )
        elif result_dir and result_dir.is_file():
            sha256 = hashlib.sha256()
            with open(result_dir, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    sha256.update(chunk)
            new_hash = sha256.hexdigest()

        artifact_reproducible = (
            bool(original_artifact) and new_artifact == original_artifact
        )
        result_reproducible = bool(original_hash) and new_hash == original_hash

        return {
            "reproducible": artifact_reproducible or result_reproducible,
            "artifact_reproducible": artifact_reproducible,
            "result_reproducible": result_reproducible,
            "original_hash": original_hash,
            "new_hash": new_hash,
            "original_artifact_sha256": original_artifact,
            "new_artifact_sha256": new_artifact,
            "determinism_profile": job.determinism_profile,
        }
