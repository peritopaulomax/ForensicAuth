"""Bootstrap the sole ForensicAuth administrator.

Usage:
    python scripts/seed_users.py

Creates or resets the only authorized user:
    paulo.pmgir — admin (password via Primeiro Acesso)

Removes all other users and reassigns their FK references to paulo.pmgir.
"""

import os
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "backend"))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.database import Base
from app.db_migrations import ensure_password_set_column
from models.user import User
from services.user_service import unset_password_hash

SOLE_ADMIN = {
    "username": "paulo.pmgir",
    "email": "paulo.pmgir@pf.gov.br",
    "role": "admin",
}


def upsert_sole_admin(db) -> User:
    """Create or reset paulo.pmgir as the only admin awaiting first access."""
    user = db.query(User).filter(User.username == SOLE_ADMIN["username"]).first()
    if user:
        user.email = SOLE_ADMIN["email"]
        user.role = SOLE_ADMIN["role"]
        user.is_active = True
        user.hashed_password = unset_password_hash()
        user.password_set = False
        print(f"Reset '{SOLE_ADMIN['username']}' — primeiro acesso pendente")
        return user

    user = User(
        id=uuid.uuid4(),
        username=SOLE_ADMIN["username"],
        email=SOLE_ADMIN["email"],
        hashed_password=unset_password_hash(),
        password_set=False,
        role=SOLE_ADMIN["role"],
        is_active=True,
    )
    db.add(user)
    db.flush()
    print(f"Created '{SOLE_ADMIN['username']}' (admin) — primeiro acesso pendente")
    return user


def remove_other_users(db, keep_user_id: uuid.UUID) -> int:
    removed = (
        db.query(User)
        .filter(User.id != keep_user_id)
        .delete(synchronize_session=False)
    )
    return removed


def main():
    settings = get_settings()
    connect_args = {"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}
    engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)
    Base.metadata.create_all(bind=engine)
    ensure_password_set_column(engine)

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()

    admin = upsert_sole_admin(db)
    removed = remove_other_users(db, admin.id)

    db.commit()
    db.close()

    print(f"Removed {removed} other user(s).")
    print("\nUnico administrador: paulo.pmgir")
    print("Acesse Primeiro Acesso na tela de login para criar a senha.")


if __name__ == "__main__":
    main()
