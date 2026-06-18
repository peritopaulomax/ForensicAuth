"""E2E test server — starts backend with temp SQLite DB and a test user."""

import os
import sys
import uuid
import tempfile

# Add src/backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "backend"))

import bcrypt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from models.user import User


def setup_db(db_path: str):
    """Create tables and a test user."""
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()

    # Create test user if not exists
    existing = db.query(User).filter(User.username == "paulo.pmgir").first()
    if not existing:
        user = User(
            id=uuid.uuid4(),
            username="paulo.pmgir",
            email="paulo.pmgir@pf.gov.br",
            hashed_password=bcrypt.hashpw("E2ESenha123!".encode(), bcrypt.gensalt()).decode(),
            password_set=True,
            role="admin",
            is_active=True,
        )
        db.add(user)
        db.commit()
    db.close()
    engine.dispose()
    print(f"E2E DB ready: {db_path}")


if __name__ == "__main__":
    import uvicorn

    db_path = os.path.join(tempfile.gettempdir(), "forensic_auth_e2e.db")
    setup_db(db_path)

    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    os.environ["SECRET_KEY"] = "e2e-secret-key-2026"
    os.environ["UPLOAD_DIR"] = os.path.join(tempfile.gettempdir(), "forensic_auth_e2e_uploads")
    os.environ["RESULTS_DIR"] = os.path.join(tempfile.gettempdir(), "forensic_auth_e2e_results")

    uvicorn.run("app.main:app", host="127.0.0.1", port=8001, log_level="warning")
