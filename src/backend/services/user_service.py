"""User management service (admin provisioning and password reset)."""

import uuid

import bcrypt
from fastapi import HTTPException
from sqlalchemy.orm import Session

from models.user import User
from services.auth_service import AuthService, PermissionDenied

# Placeholder hash for users awaiting first-access password setup.
UNSET_PASSWORD_PLAIN = "__FORENSIC_AUTH_UNSET_PASSWORD__"


def unset_password_hash() -> str:
    return bcrypt.hashpw(UNSET_PASSWORD_PLAIN.encode(), bcrypt.gensalt(rounds=12)).decode()


class UserService:
    def __init__(self, db: Session):
        self.db = db
        self.auth = AuthService(db)

    def list_users(self) -> list[User]:
        return self.db.query(User).order_by(User.username).all()

    def get_user(self, user_id: uuid.UUID) -> User | None:
        return self.db.query(User).filter(User.id == user_id).first()

    def provision_user(self, data: dict, current_user: User) -> User:
        """Create an authorized user without a password (first-access required)."""
        if current_user.role != "admin":
            raise PermissionDenied("Acesso negado para este recurso")

        if self.db.query(User).filter(User.username == data["username"]).first():
            raise HTTPException(status_code=409, detail="Username ja existe")

        if self.db.query(User).filter(User.email == data["email"]).first():
            raise HTTPException(status_code=409, detail="Email ja cadastrado")

        role = data["role"]
        if role not in ("admin", "perito"):
            raise HTTPException(status_code=422, detail="Perfil invalido")

        user = User(
            id=uuid.uuid4(),
            username=data["username"],
            email=data["email"],
            hashed_password=unset_password_hash(),
            password_set=False,
            role=role,
            is_active=True,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def update_user(self, user_id: uuid.UUID, data: dict, current_user: User) -> User:
        if current_user.role != "admin":
            raise PermissionDenied("Acesso negado para este recurso")

        user = self.get_user(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="Usuario nao encontrado")

        if user.id == current_user.id and data.get("is_active") is False:
            raise HTTPException(status_code=422, detail="Nao e possivel desativar o proprio usuario")

        if "email" in data and data["email"] != user.email:
            existing = self.db.query(User).filter(User.email == data["email"]).first()
            if existing:
                raise HTTPException(status_code=409, detail="Email ja cadastrado")
            user.email = data["email"]

        if "role" in data:
            role = data["role"]
            if role not in ("admin", "perito"):
                raise HTTPException(status_code=422, detail="Perfil invalido")
            if user.id == current_user.id and role != "admin":
                raise HTTPException(status_code=422, detail="Nao e possivel alterar o proprio perfil")
            user.role = role

        if "is_active" in data:
            user.is_active = bool(data["is_active"])

        self.db.commit()
        self.db.refresh(user)
        return user

    def reset_password(self, user_id: uuid.UUID, current_user: User) -> User:
        """Force user to set a new password via first-access flow."""
        if current_user.role != "admin":
            raise PermissionDenied("Acesso negado para este recurso")

        user = self.get_user(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="Usuario nao encontrado")

        user.hashed_password = unset_password_hash()
        user.password_set = False
        self.db.commit()
        self.db.refresh(user)
        return user
