"""drop legacy reports table (laudo unificado fora de escopo)

Revision ID: 20260730_drop_reports
Revises: 20260728_refresh
Create Date: 2026-07-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect, text

# revision identifiers, used by Alembic.
revision: str = "20260730_drop_reports"
down_revision: Union[str, Sequence[str], None] = "20260728_refresh"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Remove residual ``reports`` table if present (no product API/feature)."""
    connection = op.get_bind()
    inspector = inspect(connection)
    if "reports" not in inspector.get_table_names():
        return
    # Prefer IF EXISTS for safety across dialects.
    connection.execute(text("DROP TABLE IF EXISTS reports"))


def downgrade() -> None:
    """No recreate: laudo unificado permanece fora de escopo do produto."""
    pass
