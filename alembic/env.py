from logging.config import fileConfig
import os

from sqlalchemy import engine_from_config, pool

from alembic import context

# Load project .env so DATABASE_URL is available
from dotenv import load_dotenv

load_dotenv()

# Import Base metadata for autogenerate
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "backend"))

# Import all models so Base.metadata is fully populated
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

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# target_metadata for autogenerate support
target_metadata = Base.metadata


def get_database_url() -> str:
    """Resolve DATABASE_URL from environment or alembic.ini."""
    return os.environ.get("DATABASE_URL") or config.get_main_option("sqlalchemy.url")


def run_migrations_offline() -> None:
    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = get_database_url()
    connectable = engine_from_config(
        {"sqlalchemy.url": url},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
