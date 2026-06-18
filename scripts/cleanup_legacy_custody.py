"""Remove legacy custody records (auto-logged analysis jobs) and rebuild chains.

Before our policy change, every analysis run created analysis_started /
analysis_completed / analysis_failed records. This script deletes only those
types and re-links the remaining chain (upload, delete, future derivatives).

Usage:
    python scripts/cleanup_legacy_custody.py
    python scripts/cleanup_legacy_custody.py --dry-run
"""

import argparse
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent / "src" / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.database import Base
from models.custody_record import CustodyRecord
from services.custody_service import CustodyService

LEGACY_TYPES = ("analysis_started", "analysis_completed", "analysis_failed")


def resolve_database_url(cli_url: str | None) -> str:
    """Use CLI URL, else src/backend/.env (ignores shell DATABASE_URL for this script)."""
    if cli_url:
        return cli_url
    env_file = BACKEND_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("DATABASE_URL="):
                url = line.split("=", 1)[1].strip().strip('"').strip("'")
                if url.startswith("sqlite:///./"):
                    db_path = BACKEND_DIR / url.replace("sqlite:///./", "")
                    return f"sqlite:///{db_path.as_posix()}"
                return url
    raise SystemExit("DATABASE_URL not found. Pass --database-url or configure src/backend/.env")


def _drop_immutability_trigger(conn) -> None:
    conn.execute(text("DROP TRIGGER IF EXISTS trg_custody_immutable"))


def _create_immutability_trigger(conn) -> None:
    conn.execute(
        text("""
            CREATE TRIGGER IF NOT EXISTS trg_custody_immutable
            BEFORE UPDATE ON custody_records
            BEGIN
                SELECT RAISE(IGNORE);
            END;
        """)
    )


def rebuild_case_chain(db, case_id, service: CustodyService) -> int:
    """Recompute previous_record_hash and record_hash for all records in a case."""
    records = (
        db.query(CustodyRecord)
        .filter(CustodyRecord.case_id == case_id)
        .order_by(CustodyRecord.timestamp.asc())
        .all()
    )
    prev_hash = None
    for record in records:
        record.previous_record_hash = prev_hash
        record.record_hash = service._compute_hash(record)
        prev_hash = record.record_hash
    return len(records)


def main():
    parser = argparse.ArgumentParser(description="Remove legacy analysis custody records")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show counts only, do not delete or rebuild",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="Override database URL (default: src/backend/.env)",
    )
    args = parser.parse_args()

    database_url = resolve_database_url(args.database_url)
    print(f"Database: {database_url}")

    connect_args = {"check_same_thread": False} if "sqlite" in database_url else {}
    engine = create_engine(database_url, connect_args=connect_args)
    Base.metadata.create_all(bind=engine)

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()

    legacy = (
        db.query(CustodyRecord)
        .filter(CustodyRecord.record_type.in_(LEGACY_TYPES))
        .all()
    )
    case_ids = {r.case_id for r in legacy}

    print(f"Legacy records found: {len(legacy)}")
    for t in LEGACY_TYPES:
        n = sum(1 for r in legacy if r.record_type == t)
        if n:
            print(f"  - {t}: {n}")
    print(f"Affected cases: {len(case_ids)}")

    if args.dry_run:
        db.close()
        print("Dry run — no changes made.")
        return

    if not legacy:
        print("Nothing to clean up.")
        db.close()
        return

    deleted = (
        db.query(CustodyRecord)
        .filter(CustodyRecord.record_type.in_(LEGACY_TYPES))
        .delete(synchronize_session=False)
    )
    db.commit()
    print(f"Deleted {deleted} legacy record(s).")

    service = CustodyService(db)
    is_sqlite = engine.dialect.name == "sqlite"

    if is_sqlite:
        with engine.connect() as conn:
            _drop_immutability_trigger(conn)
            conn.commit()

    rebuilt = 0
    for case_id in case_ids:
        rebuilt += rebuild_case_chain(db, case_id, service)
    db.commit()

    if is_sqlite:
        with engine.connect() as conn:
            _create_immutability_trigger(conn)
            conn.commit()

    print(f"Rebuilt chain for {len(case_ids)} case(s) ({rebuilt} record(s) re-hashed).")

    verify = CustodyService(db)
    all_valid = True
    for case_id in case_ids:
        result = verify.verify_chain(case_id)
        if not result["valid"]:
            all_valid = False
            print(f"  WARNING: case {case_id} chain invalid after rebuild")
    if all_valid:
        print("All affected case chains verify OK.")

    db.close()
    print("Done.")


if __name__ == "__main__":
    main()
