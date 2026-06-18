"""Wipe forensic operational data (cases, evidence, jobs) and storage files.

Usage:
    python scripts/cleanup_forensic_data.py

Keeps users intact. Removes all cases, evidences, analysis jobs, custody
records, reports, and files under UPLOAD_DIR / RESULTS_DIR / DERIVATIVES_DIR.
"""

import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "backend"))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.database import Base
from models.analysis_job import AnalysisJob
from models.case import Case
from models.custody_record import CustodyRecord
from models.evidence import Evidence
from models.report import Report


def _clear_directory(path: Path) -> int:
    if not path.exists():
        return 0
    removed = 0
    for item in path.iterdir():
        if item.is_file():
            item.unlink()
            removed += 1
        elif item.is_dir():
            shutil.rmtree(item)
            removed += 1
    return removed


def cleanup_database(db) -> dict:
    counts = {}
    counts["analysis_jobs"] = db.query(AnalysisJob).delete(synchronize_session=False)
    # Custody may be protected by SQLite trigger — use raw delete
    try:
        counts["custody_records"] = db.query(CustodyRecord).delete(synchronize_session=False)
    except Exception:
        db.execute(text("DELETE FROM custody_records"))
        counts["custody_records"] = db.execute(text("SELECT changes()")).scalar()
    counts["reports"] = db.query(Report).delete(synchronize_session=False)
    counts["evidences"] = db.query(Evidence).delete(synchronize_session=False)
    counts["cases"] = db.query(Case).delete(synchronize_session=False)
    db.commit()
    return counts


def main():
    settings = get_settings()
    connect_args = {"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}
    engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)
    Base.metadata.create_all(bind=engine)

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()

    db_counts = cleanup_database(db)
    db.close()

    upload_dir = Path(settings.UPLOAD_DIR)
    results_dir = Path(settings.RESULTS_DIR)
    derivatives_dir = Path(settings.DERIVATIVES_DIR)
    backend_results = Path(__file__).resolve().parent.parent / "src" / "backend" / "results"
    backend_derivatives = Path(__file__).resolve().parent.parent / "src" / "backend" / "derivatives"
    root_uploads = Path(__file__).resolve().parent.parent / "uploads"
    root_results = Path(__file__).resolve().parent.parent / "results"
    root_derivatives = Path(__file__).resolve().parent.parent / "derivatives"

    file_counts = {
        "upload_dir": _clear_directory(upload_dir),
        "results_dir": _clear_directory(results_dir),
        "derivatives_dir": _clear_directory(derivatives_dir),
        "backend_results": _clear_directory(backend_results) if backend_results.exists() else 0,
        "backend_derivatives": _clear_directory(backend_derivatives) if backend_derivatives.exists() else 0,
        "root_uploads": _clear_directory(root_uploads) if root_uploads.exists() else 0,
        "root_results": _clear_directory(root_results) if root_results.exists() else 0,
        "root_derivatives": _clear_directory(root_derivatives) if root_derivatives.exists() else 0,
    }

    print("Forensic data cleanup complete.")
    print("Database:", db_counts)
    print("Files removed:", file_counts)


if __name__ == "__main__":
    main()
