#!/usr/bin/env python3
"""Apply custody lifecycle schema upgrades (shares, closures, Ed25519 columns).

Uses src/backend/.env (typically SQLite). Run from project root:

  conda activate forensicauth
  python scripts/migrate_custody_lifecycle.py

Migrations also run automatically when the API starts (app lifespan).
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "src" / "backend"
sys.path.insert(0, str(BACKEND))

# Load backend .env before engine (avoids picking root .env with PostgreSQL)
from dotenv import load_dotenv

load_dotenv(BACKEND / ".env", override=True)

from app.config import get_settings
from app.database import engine
from app.db_migrations import (
    ensure_custody_lifecycle_tables,
    ensure_custody_signing_columns,
)


def main() -> None:
    settings = get_settings()
    url = settings.DATABASE_URL
    display = url.split("@")[-1] if "@" in url else url
    print(f"Database: {display}")
    print("Applying custody lifecycle migrations...")
    try:
        ensure_custody_signing_columns(engine)
        ensure_custody_lifecycle_tables(engine)
    except Exception as exc:
        if "Connection refused" in str(exc) or "OperationalError" in type(exc).__name__:
            print(
                "\nErro: nao foi possivel conectar ao banco.\n"
                "- Se usa SQLite (src/backend/.env), execute este script na raiz do projeto.\n"
                "- Se usa PostgreSQL, inicie o servidor (docker compose up -d db) ou ajuste DATABASE_URL.\n"
                "- Alternativa: reinicie o backend em src/backend — as migracoes rodam no startup.\n"
            )
        raise
    print("Done.")


if __name__ == "__main__":
    main()
