"""Diagnostico de genesis da cadeia de custodia por caso."""
from __future__ import annotations

import sys
from collections import Counter

from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, ".")

from models.custody_record import CustodyRecord
from models.case import Case
from services.custody_service import CustodyService


def main() -> None:
    engine = create_engine("sqlite:///./forensicauth_dev.db")
    db = sessionmaker(bind=engine)()
    svc = CustodyService(db)

    total = db.query(CustodyRecord).count()
    print(f"total_custody_records={total}")

    rows = (
        db.query(CustodyRecord.case_id, func.count())
        .group_by(CustodyRecord.case_id)
        .order_by(func.count().desc())
        .all()
    )
    for case_id, n in rows[:5]:
        case = db.query(Case).filter(Case.id == case_id).first()
        title = case.protocol_number if case else str(case_id)
        recs = db.query(CustodyRecord).filter(CustodyRecord.case_id == case_id).all()
        genesis = [r for r in recs if not (r.previous_record_hash or "").strip()]
        print(f"\n=== {title} records={n} genesis_count={len(genesis)} ===")
        if len(genesis) != 1:
            for g in genesis[:15]:
                print(
                    f"  GEN {str(g.id)[:8]} type={g.record_type} seq={g.chain_sequence} "
                    f"ts={g.timestamp}"
                )
            if len(genesis) == 0:
                print("  (zero genesis — amostra de previous_record_hash)")
                for r in sorted(recs, key=lambda x: (x.timestamp or "", str(x.id)))[:5]:
                    prev = r.previous_record_hash
                    print(
                        f"    {str(r.id)[:8]} seq={r.chain_sequence} "
                        f"prev={'NULL' if prev is None else repr(prev)[:24]}"
                    )
        result = svc.verify_chain(case_id)
        print(f"  verify_chain: valid={result['valid']} reason={result.get('reason')}")


if __name__ == "__main__":
    main()
