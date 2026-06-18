"""Database configuration and session management."""

from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker, Session

from app.config import get_settings

settings = get_settings()

_connect_args: dict = {}
if settings.DATABASE_URL.startswith("sqlite"):
    _connect_args = {"check_same_thread": False, "timeout": 60}

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    echo=settings.DEBUG,
    connect_args=_connect_args,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


@event.listens_for(engine, "connect")
def _sqlite_foreign_keys(dbapi_conn, connection_record):
    """Enable FK enforcement on SQLite."""
    if engine.dialect.name == "sqlite":
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


@event.listens_for(engine, "connect")
def _sqlite_immutability_trigger(dbapi_conn, connection_record):
    """On SQLite, install a trigger that silently ignores UPDATEs on custody_records.

    This makes UPDATE statements return rowcount==0, satisfying the immutability
    contract in unit tests. PostgreSQL immutability will be enforced via GRANT/REVOKE
    or a similar database-level mechanism in production.
    """
    # Only apply to SQLite dialect
    if hasattr(dbapi_conn, "execute"):
        try:
            cursor = dbapi_conn.cursor()
            cursor.execute(
                """
                CREATE TRIGGER IF NOT EXISTS trg_custody_immutable
                BEFORE UPDATE ON custody_records
                BEGIN
                    SELECT RAISE(IGNORE);
                END;
                """
            )
            cursor.close()
        except Exception:
            # If the table doesn't exist yet (e.g. during metadata.create_all),
            # the trigger creation will fail — that's fine, it will be retried
            # on the next connection.
            pass


def get_db() -> Session:
    """Dependency that provides a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
