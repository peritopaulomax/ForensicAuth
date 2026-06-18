"""Authentication service."""

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import HTTPException, status
from jose import jwt, JWTError
from sqlalchemy.orm import Session

from app.config import get_settings
from models.user import User


@dataclass
class AuthResult:
    user: User
    token: str


class AuthenticationError(Exception):
    pass


class PermissionDenied(Exception):
    pass


class AuthService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    def hash_password(self, password: str) -> str:
        """Hash a password using bcrypt."""
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash."""
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))

    def validate_password_strength(self, password: str) -> tuple[bool, str]:
        """Validate password strength."""
        if len(password) < 8:
            return False, "Senha menor que o minimo: deve ter pelo menos 8 caracteres, 1 maiuscula e 1 numero"
        if not re.search(r"[A-Z]", password):
            return False, "Senha deve conter pelo menos 1 letra maiuscula e 1 numero"
        if not re.search(r"\d", password):
            return False, "Senha deve conter pelo menos 1 numero"
        return True, ""

    def create_access_token(self, data: dict) -> str:
        """Create a JWT access token."""
        to_encode = data.copy()
        expire = datetime.now(timezone.utc) + timedelta(minutes=self.settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, self.settings.SECRET_KEY, algorithm=self.settings.ALGORITHM)
        return encoded_jwt

    def verify_token(self, token: str) -> dict:
        """Verify and decode a JWT token."""
        try:
            payload = jwt.decode(token, self.settings.SECRET_KEY, algorithms=[self.settings.ALGORITHM])
            return payload
        except JWTError:
            raise AuthenticationError("Token de autenticacao invalido")

    def authenticate(self, username: str, password: str) -> AuthResult:
        """Authenticate a user and return user + token."""
        user = self.db.query(User).filter(User.username == username).first()

        if not user:
            raise AuthenticationError("Usuario ou senha incorretos")

        if not user.is_active:
            raise AuthenticationError("Usuario inativo")

        if not user.password_set:
            raise AuthenticationError(
                "Senha nao definida. Use Primeiro Acesso para criar sua senha."
            )

        if not self.verify_password(password, user.hashed_password):
            raise AuthenticationError("Usuario ou senha incorretos")

        token = self.create_access_token(
            {"sub": str(user.id), "role": user.role}
        )
        return AuthResult(user=user, token=token)

    def first_access(self, username: str, password: str, password_confirm: str) -> User:
        """Set initial password for a pre-provisioned user."""
        if password != password_confirm:
            raise AuthenticationError("As senhas nao coincidem")

        valid, msg = self.validate_password_strength(password)
        if not valid:
            raise HTTPException(status_code=422, detail=msg)

        user = self.db.query(User).filter(User.username == username).first()
        if not user or not user.is_active or user.password_set:
            raise AuthenticationError(
                "Usuario invalido ou senha ja definida. Verifique o username ou faca login."
            )

        user.hashed_password = self.hash_password(password)
        user.password_set = True
        self.db.commit()
        self.db.refresh(user)
        return user

    def register(self, data: dict, current_user: User) -> User:
        """Register a new user with password (admin only, legacy endpoint)."""
        if current_user.role != "admin":
            raise PermissionDenied("Acesso negado para este recurso")

        valid, msg = self.validate_password_strength(data["password"])
        if not valid:
            raise HTTPException(status_code=422, detail=msg)

        existing_username = self.db.query(User).filter(User.username == data["username"]).first()
        if existing_username:
            raise HTTPException(status_code=409, detail="Username ja existe")

        existing_email = self.db.query(User).filter(User.email == data["email"]).first()
        if existing_email:
            raise HTTPException(status_code=409, detail="Email ja cadastrado")

        user = User(
            id=uuid.uuid4(),
            username=data["username"],
            email=data["email"],
            hashed_password=self.hash_password(data["password"]),
            password_set=True,
            role=data["role"],
            is_active=True,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user
