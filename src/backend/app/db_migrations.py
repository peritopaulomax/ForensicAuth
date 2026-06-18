"""Lightweight schema upgrades for existing databases (no Alembic revision yet)."""

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def ensure_password_set_column(engine: Engine) -> None:
    """Add users.password_set if the table predates first-access support."""
    inspector = inspect(engine)
    if "users" not in inspector.get_table_names():
        return
    columns = {c["name"] for c in inspector.get_columns("users")}
    if "password_set" in columns:
        return
    with engine.connect() as conn:
        if engine.dialect.name == "sqlite":
            conn.execute(
                text(
                    "ALTER TABLE users ADD COLUMN password_set BOOLEAN NOT NULL DEFAULT 1"
                )
            )
        else:
            conn.execute(
                text(
                    "ALTER TABLE users ADD COLUMN password_set BOOLEAN NOT NULL DEFAULT TRUE"
                )
            )
        conn.commit()


def _timestamp_column_sql(engine: Engine) -> str:
    if engine.dialect.name == "sqlite":
        return "DATETIME"
    return "TIMESTAMP"


def _uuid_column_sql(engine: Engine) -> str:
    if engine.dialect.name == "sqlite":
        return "UUID"
    return "UUID"


def ensure_evidence_soft_delete_columns(engine: Engine) -> None:
    """Add evidences.deleted_at / deleted_by for soft-delete custody support."""
    inspector = inspect(engine)
    if "evidences" not in inspector.get_table_names():
        return
    columns = {c["name"] for c in inspector.get_columns("evidences")}
    ts_type = _timestamp_column_sql(engine)
    uuid_type = _uuid_column_sql(engine)
    with engine.connect() as conn:
        if "deleted_at" not in columns:
            conn.execute(text(f"ALTER TABLE evidences ADD COLUMN deleted_at {ts_type}"))
        if "deleted_by" not in columns:
            conn.execute(text(f"ALTER TABLE evidences ADD COLUMN deleted_by {uuid_type}"))
        conn.commit()


def ensure_case_soft_delete_columns(engine: Engine) -> None:
    """Add cases.deleted_at / deleted_by for soft-delete with custody preservation."""
    inspector = inspect(engine)
    if "cases" not in inspector.get_table_names():
        return
    columns = {c["name"] for c in inspector.get_columns("cases")}
    ts_type = _timestamp_column_sql(engine)
    uuid_type = _uuid_column_sql(engine)
    with engine.connect() as conn:
        if "deleted_at" not in columns:
            conn.execute(text(f"ALTER TABLE cases ADD COLUMN deleted_at {ts_type}"))
        if "deleted_by" not in columns:
            conn.execute(text(f"ALTER TABLE cases ADD COLUMN deleted_by {uuid_type}"))
        conn.commit()


def ensure_custody_job_fk_on_delete_set_null(engine: Engine) -> None:
    """Garante que apagar analysis_jobs nao bloqueie a cadeia (job_id -> NULL)."""
    if engine.dialect.name != "postgresql":
        return
    inspector = inspect(engine)
    if "custody_records" not in inspector.get_table_names():
        return
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT c.conname, pg_get_constraintdef(c.oid) AS def
                FROM pg_constraint c
                JOIN pg_class t ON c.conrelid = t.oid
                WHERE t.relname = 'custody_records'
                  AND c.contype = 'f'
                  AND pg_get_constraintdef(c.oid) LIKE '%analysis_jobs%'
                """
            )
        ).fetchone()
        if not row:
            return
        conname, definition = row[0], (row[1] or "").upper()
        if "ON DELETE SET NULL" in definition:
            return
        conn.execute(text(f'ALTER TABLE custody_records DROP CONSTRAINT "{conname}"'))
        conn.execute(
            text(
                """
                ALTER TABLE custody_records
                ADD CONSTRAINT custody_records_job_id_fkey
                FOREIGN KEY (job_id) REFERENCES analysis_jobs(id) ON DELETE SET NULL
                """
            )
        )
        conn.commit()


def ensure_custody_chain_sequence_column(engine: Engine) -> None:
    """Garante coluna chain_sequence e reconcilia 1..n na ordem criptografica (sem quebrar hash)."""
    from sqlalchemy.orm import sessionmaker

    from models.custody_record import CustodyRecord
    from services.custody_service import CustodyService

    inspector = inspect(engine)
    if "custody_records" not in inspector.get_table_names():
        return

    columns = {c["name"] for c in inspector.get_columns("custody_records")}
    with engine.connect() as conn:
        if "chain_sequence" not in columns:
            conn.execute(
                text(
                    "ALTER TABLE custody_records ADD COLUMN chain_sequence INTEGER NOT NULL DEFAULT 0"
                )
            )
            conn.commit()

    Session = sessionmaker(bind=engine)
    db = Session()
    sqlite = engine.dialect.name == "sqlite"
    if sqlite:
        db.execute(text("DROP TRIGGER IF EXISTS trg_custody_immutable"))
        db.commit()
    try:
        CustodyService(db).reconcile_all_chain_sequence_metadata()
        db.commit()
    finally:
        if sqlite:
            db.execute(
                text(
                    """
                    CREATE TRIGGER IF NOT EXISTS trg_custody_immutable
                    BEFORE UPDATE ON custody_records
                    BEGIN
                        SELECT RAISE(IGNORE);
                    END;
                    """
                )
            )
            db.commit()
        db.close()


def ensure_custody_signing_columns(engine: Engine) -> None:
    """Add Ed25519 signature columns to custody_records."""
    inspector = inspect(engine)
    if "custody_records" not in inspector.get_table_names():
        return
    columns = {c["name"] for c in inspector.get_columns("custody_records")}
    with engine.connect() as conn:
        if "system_signature" not in columns:
            conn.execute(text("ALTER TABLE custody_records ADD COLUMN system_signature TEXT"))
        if "signing_key_id" not in columns:
            conn.execute(
                text("ALTER TABLE custody_records ADD COLUMN signing_key_id VARCHAR(64)")
            )
        conn.commit()


def ensure_custody_lifecycle_tables(engine: Engine) -> None:
    """Create case_shares, case_closures, case_closure_signatures if missing."""
    from app.database import Base
    import models  # noqa: F401 — register models

    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    needed = {"case_shares", "case_closures", "case_closure_signatures"}
    if needed.issubset(existing):
        return
    Base.metadata.create_all(
        bind=engine,
        tables=[
            Base.metadata.tables["case_shares"],
            Base.metadata.tables["case_closures"],
            Base.metadata.tables["case_closure_signatures"],
        ],
    )


def ensure_analysis_job_progress_columns(engine: Engine) -> None:
    """Add analysis_jobs.progress / progress_message for real-time UI updates."""
    inspector = inspect(engine)
    if "analysis_jobs" not in inspector.get_table_names():
        return
    columns = {c["name"] for c in inspector.get_columns("analysis_jobs")}
    with engine.connect() as conn:
        if "progress" not in columns:
            conn.execute(
                text("ALTER TABLE analysis_jobs ADD COLUMN progress INTEGER NOT NULL DEFAULT 0")
            )
        if "progress_message" not in columns:
            conn.execute(
                text(
                    "ALTER TABLE analysis_jobs ADD COLUMN progress_message VARCHAR(512) NOT NULL DEFAULT ''"
                )
            )
        conn.commit()


def ensure_analysis_job_reproducibility_columns(engine: Engine) -> None:
    """Add runtime_manifest / artifact_sha256 for forensic reproducibility."""
    inspector = inspect(engine)
    if "analysis_jobs" not in inspector.get_table_names():
        return
    columns = {c["name"] for c in inspector.get_columns("analysis_jobs")}
    with engine.connect() as conn:
        if "artifact_sha256" not in columns:
            conn.execute(text("ALTER TABLE analysis_jobs ADD COLUMN artifact_sha256 VARCHAR(64)"))
        if "runtime_manifest" not in columns:
            if engine.dialect.name == "sqlite":
                conn.execute(text("ALTER TABLE analysis_jobs ADD COLUMN runtime_manifest JSON"))
            else:
                conn.execute(text("ALTER TABLE analysis_jobs ADD COLUMN runtime_manifest JSONB"))
        if "determinism_profile" not in columns:
            conn.execute(text("ALTER TABLE analysis_jobs ADD COLUMN determinism_profile VARCHAR(32)"))
        conn.commit()


def ensure_case_storage_mode_column(engine: Engine) -> None:
    """Add cases.storage_mode for native Peritus vs VA case packages."""
    inspector = inspect(engine)
    if "cases" not in inspector.get_table_names():
        return
    columns = {c["name"] for c in inspector.get_columns("cases")}
    if "storage_mode" in columns:
        return
    with engine.connect() as conn:
        conn.execute(
            text(
                "ALTER TABLE cases ADD COLUMN storage_mode VARCHAR(20) NOT NULL DEFAULT 'va'"
            )
        )
        conn.commit()


def ensure_migrate_analista_to_perito(engine: Engine) -> None:
    """Remove legacy analista role — migrate existing users to perito."""
    inspector = inspect(engine)
    if "users" not in inspector.get_table_names():
        return
    with engine.connect() as conn:
        conn.execute(text("UPDATE users SET role = 'perito' WHERE role = 'analista'"))
        conn.commit()


def ensure_migrate_em_andamento_to_aberto(engine: Engine) -> None:
    """Caso aberto engloba em andamento — normaliza registros legados."""
    inspector = inspect(engine)
    if "cases" not in inspector.get_table_names():
        return
    with engine.connect() as conn:
        conn.execute(
            text("UPDATE cases SET status = 'aberto' WHERE status = 'em_andamento'")
        )
        conn.commit()
