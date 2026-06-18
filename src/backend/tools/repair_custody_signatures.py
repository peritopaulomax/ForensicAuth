"""Correcao pontual de assinaturas Ed25519 (operador, nao startup).

Uso (a partir de src/backend, com conda activate forensicauth):

  python tools/repair_custody_signatures.py --dry-run
  python tools/repair_custody_signatures.py --confirm
  python tools/repair_custody_signatures.py --confirm --case-id <uuid>

Re-assina system_signature com a chave persistente atual (record_hash inalterado).
Exige cadeia valida. Registra evento custody_signing_repair na cadeia apos a correcao.
"""
from __future__ import annotations

import argparse
import sys
import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from models.custody_record import CustodyRecord
from models.user import User
from services.custody_service import CustodyService, _allow_custody_record_updates
from services.custody_signing_service import CustodySigningService, dev_signing_key_path
from services.forensic_integrity_service import ForensicIntegrityService


def _invalid_signature_count(db, case_id: uuid.UUID) -> tuple[int, int]:
    signing = CustodySigningService()
    records = (
        db.query(CustodyRecord)
        .filter(CustodyRecord.case_id == case_id)
        .order_by(CustodyRecord.chain_sequence.asc())
        .all()
    )
    checked = 0
    invalid = 0
    for rec in records:
        if not rec.system_signature or not rec.record_hash:
            continue
        checked += 1
        if not signing.verify_digest_hex(
            rec.record_hash, rec.system_signature, rec.signing_key_id
        ):
            invalid += 1
    return checked, invalid


def repair_case_signatures(
    db,
    case_id: uuid.UUID,
    *,
    dry_run: bool,
    actor_user_id: uuid.UUID | None,
) -> dict:
    svc = CustodyService(db)
    chain = svc.verify_chain(case_id)
    if not chain.get("valid"):
        return {
            "case_id": str(case_id),
            "ok": False,
            "error": "chain_invalid",
            "chain": chain,
        }

    checked, invalid = _invalid_signature_count(db, case_id)
    if invalid == 0:
        return {
            "case_id": str(case_id),
            "ok": True,
            "skipped": True,
            "reason": "signatures_already_valid",
            "checked": checked,
        }

    records = (
        db.query(CustodyRecord)
        .filter(CustodyRecord.case_id == case_id)
        .order_by(CustodyRecord.chain_sequence.asc())
        .all()
    )

    if dry_run:
        return {
            "case_id": str(case_id),
            "ok": True,
            "dry_run": True,
            "would_resign": len(records),
            "invalid_before": invalid,
            "checked": checked,
        }

    signing = CustodySigningService()
    with _allow_custody_record_updates(db):
        for record in records:
            if not record.record_hash:
                continue
            signed = signing.sign_digest_hex(record.record_hash)
            record.system_signature = signed["signature_b64"]
            record.signing_key_id = signed["signing_key_id"]
    db.flush()

    audit_record = None
    if actor_user_id:
        audit_record = svc.create_record(
            record_type="custody_signing_repair",
            case_id=case_id,
            user_id=actor_user_id,
            details={
                "reason": "legacy_ephemeral_signing_key",
                "records_resigned": len(records),
                "invalid_signatures_before": invalid,
                "signing_key_id": signing.key_id,
                "tool": "repair_custody_signatures.py",
            },
        )

    report = ForensicIntegrityService(db).verify_case_forensic_integrity(case_id)
    return {
        "case_id": str(case_id),
        "ok": True,
        "resigned": len(records),
        "invalid_before": invalid,
        "forensic_valid": report.get("valid"),
        "invalid_sigs_after": len(report.get("signatures", {}).get("invalid", [])),
        "audit_record_id": str(audit_record.id) if audit_record else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Aplica re-assinatura (sem isso, apenas --dry-run e permitido)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Mostra o que seria feito sem gravar",
    )
    parser.add_argument("--case-id", type=str, default="", help="UUID do caso (opcional)")
    args = parser.parse_args()

    if not args.confirm and not args.dry_run:
        print("Use --dry-run ou --confirm", file=sys.stderr)
        return 2

    settings = get_settings()
    key_path = dev_signing_key_path(settings)
    print(f"DATABASE_URL={settings.DATABASE_URL}")
    print(f"signing_key_file={key_path} exists={key_path.is_file()}")

    engine = create_engine(settings.DATABASE_URL)
    Session = sessionmaker(bind=engine)
    db = Session()

    if args.case_id:
        case_ids = [uuid.UUID(args.case_id)]
    else:
        case_ids = [row[0] for row in db.query(CustodyRecord.case_id).distinct().all()]

    actor = (
        db.query(User)
        .filter(User.is_active, User.role == "admin")
        .order_by(User.created_at.asc())
        .first()
    )
    actor_id = actor.id if actor else None
    if not actor_id and args.confirm:
        print("AVISO: nenhum usuario admin — reparo sem registro custody_signing_repair")

    dry_run = args.dry_run or not args.confirm
    results = []
    for case_id in case_ids:
        results.append(
            repair_case_signatures(
                db, case_id, dry_run=dry_run, actor_user_id=actor_id
            )
        )

    if args.confirm:
        db.commit()
    else:
        db.rollback()

    for r in results:
        print(r)

    failed = [r for r in results if not r.get("ok")]
    if failed:
        return 1
    if args.confirm:
        bad = [r for r in results if r.get("ok") and not r.get("skipped") and not r.get("forensic_valid")]
        if bad:
            print("AVISO: verificacao forense ainda falhou em algum caso:", bad)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
