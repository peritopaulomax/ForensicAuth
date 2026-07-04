"""initial schema

Revision ID: 20260625
Revises:
Create Date: 2026-06-25 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "20260625"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Bootstrap the schema from SQLAlchemy models if tables are missing.

    For the first production setup, this creates all tables defined in
    ``Base.metadata``. Existing tables are left untouched.
    """
    connection = op.get_bind()
    inspector = inspect(connection)
    existing = set(inspector.get_table_names())

    import sys
    from pathlib import Path

    backend = Path(__file__).resolve().parents[2] / "src" / "backend"
    sys.path.insert(0, str(backend))

    from app.database import Base  # noqa: E402
    from models import (  # noqa: E402,F401
        analysis_job,
        case,
        case_closure,
        case_share,
        custody_record,
        evidence,
        report,
        user,
    )

    missing = [t for t in Base.metadata.sorted_tables if t.name not in existing]
    if missing:
        Base.metadata.create_all(connection, tables=missing)


def downgrade() -> None:
    """Downgrade is intentionally a no-op for the initial bootstrap revision.

    Dropping all tables would destroy evidence and custody records.
    """
    pass
