"""Diagnostico da cadeia de custodia (uso local)."""
from __future__ import annotations

import sys
import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models.custody_record import CustodyRecord
from services.custody_service import CustodyService

PREFIX = (sys.argv[1] if len(sys.argv) > 1 else "336d657a").lower()


def main() -> None:
    engine = create_engine("sqlite:///./forensicauth_dev.db")
    Session = sessionmaker(bind=engine)
    db = Session()
    svc = CustodyService(db)

    records = db.query(CustodyRecord).order_by(
        CustodyRecord.case_id, CustodyRecord.timestamp, CustodyRecord.id
    ).all()

    target = None
    for r in records:
        if str(r.id).lower().startswith(PREFIX):
            target = r
            break

    if not target:
        print(f"Nenhum registro com prefixo {PREFIX}")
        return

    case_id = target.case_id
    case_records = (
        db.query(CustodyRecord)
        .filter(CustodyRecord.case_id == case_id)
        .order_by(CustodyRecord.timestamp.asc(), CustodyRecord.id.asc())
        .all()
    )

    print(f"case_id={case_id} total={len(case_records)}")
    print(f"target={target.id} type={target.record_type} ts={target.timestamp}")
    print(f"  stored_prev={target.previous_record_hash}")
    print(f"  hash_ok_canonical={target.record_hash == svc._compute_hash(target)}")
    print(f"  hash_ok_legacy={target.record_hash == svc._compute_hash(target, legacy_details=True)}")

    prev_hash = None
    for i, rec in enumerate(case_records):
        stored = rec.previous_record_hash or None
        expected = prev_hash or None
        link_ok = stored == expected
        hash_ok = svc._record_hash_matches(rec)
        mark = ">>>" if str(rec.id) == str(target.id) else "   "
        if not link_ok or not hash_ok or str(rec.id) == str(target.id):
            print(
                f"{mark} [{i}] {rec.id} {rec.record_type} ts={rec.timestamp} "
                f"link={'OK' if link_ok else 'BREAK'} hash={'OK' if hash_ok else 'BAD'} "
                f"prev_stored={(stored or '')[:12]} prev_expected={(expected or '')[:12]}"
            )
        prev_hash = rec.record_hash

    result = svc.verify_chain(case_id)
    print("verify_chain:", result)


if __name__ == "__main__":
    main()
