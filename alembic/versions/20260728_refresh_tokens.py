"""add refresh_tokens table for access+refresh auth

Revision ID: 20260728_refresh
Revises: 20260625
Create Date: 2026-07-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "20260728_refresh"
down_revision: Union[str, Sequence[str], None] = "20260625"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create refresh_tokens if the table is missing."""
    connection = op.get_bind()
    inspector = inspect(connection)
    if "refresh_tokens" in inspector.get_table_names():
        return

    import sys
    from pathlib import Path

    backend = Path(__file__).resolve().parents[2] / "src" / "backend"
    sys.path.insert(0, str(backend))

    from app.database import Base  # noqa: E402
    from models import refresh_token  # noqa: E402,F401

    Base.metadata.create_all(
        connection,
        tables=[Base.metadata.tables["refresh_tokens"]],
    )


def downgrade() -> None:
    """Drop refresh_tokens (sessions become invalid)."""
    op.drop_table("refresh_tokens")
