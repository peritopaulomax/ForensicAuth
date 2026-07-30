"""Authentication service."""

import hashlib
import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import HTTPException, status
from jose import jwt, JWTError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.utils import utc_now
from models.refresh_token import RefreshToken
from models.user import User


@dataclass
class AuthResult:
    user: User
    access_token: str
    refresh_token: str
    expires_in: int

    @property
    def token(self) -> str:
        """Backward-compatible alias for access_token."""
        return self.access_token


@dataclass
class TokenPair:
    access_token: str
    refresh_token: str
    expires_in: int


class AuthenticationError(Exception):
    pass


class PermissionDenied(Exception):
    pass


def _hash_refresh_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


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
        """Create a short-lived JWT access token."""
        to_encode = data.copy()
        expire = datetime.now(timezone.utc) + timedelta(minutes=self.settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        to_encode.update({"exp": expire, "type": "access"})
        return jwt.encode(to_encode, self.settings.SECRET_KEY, algorithm=self.settings.ALGORITHM)

    def verify_token(self, token: str) -> dict:
        """Verify and decode a JWT token."""
        try:
            payload = jwt.decode(token, self.settings.SECRET_KEY, algorithms=[self.settings.ALGORITHM])
            return payload
        except JWTError:
            raise AuthenticationError("Token de autenticacao invalido")

    def _access_expires_in_seconds(self) -> int:
        return int(self.settings.ACCESS_TOKEN_EXPIRE_MINUTES) * 60

    def _issue_refresh_token(self, user: User) -> str:
        """Create an opaque refresh token and persist its hash (no commit)."""
        raw = secrets.token_urlsafe(48)
        record = RefreshToken(
            id=uuid.uuid4(),
            user_id=user.id,
            token_hash=_hash_refresh_token(raw),
            expires_at=utc_now() + timedelta(days=self.settings.REFRESH_TOKEN_EXPIRE_DAYS),
            revoked_at=None,
            replaced_by=None,
        )
        self.db.add(record)
        self.db.flush()
        return raw

    def _issue_token_pair(self, user: User) -> TokenPair:
        access = self.create_access_token({"sub": str(user.id), "role": user.role})
        refresh = self._issue_refresh_token(user)
        self.db.commit()
        return TokenPair(
            access_token=access,
            refresh_token=refresh,
            expires_in=self._access_expires_in_seconds(),
        )

    def authenticate(self, username: str, password: str) -> AuthResult:
        """Authenticate a user and return user + access/refresh tokens."""
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

        pair = self._issue_token_pair(user)
        return AuthResult(
            user=user,
            access_token=pair.access_token,
            refresh_token=pair.refresh_token,
            expires_in=pair.expires_in,
        )

    def refresh(self, refresh_token: str) -> TokenPair:
        """Validate refresh token, rotate it, and issue a new access+refresh pair."""
        if not refresh_token or not refresh_token.strip():
            raise AuthenticationError("Refresh token invalido ou expirado")

        token_hash = _hash_refresh_token(refresh_token.strip())
        record = (
            self.db.query(RefreshToken)
            .filter(RefreshToken.token_hash == token_hash)
            .first()
        )

        if record is None:
            raise AuthenticationError("Refresh token invalido ou expirado")

        now = utc_now()
        if record.revoked_at is not None:
            # Reuse of a rotated token → revoke all sessions for this user.
            if record.replaced_by is not None:
                self.revoke_all_user_tokens(record.user_id)
            raise AuthenticationError("Refresh token invalido ou expirado")

        if record.expires_at <= now:
            record.revoked_at = now
            self.db.commit()
            raise AuthenticationError("Refresh token invalido ou expirado")

        user = self.db.query(User).filter(User.id == record.user_id).first()
        if user is None or not user.is_active:
            record.revoked_at = now
            self.db.commit()
            raise AuthenticationError("Refresh token invalido ou expirado")

        # Rotate: revoke current, issue new, link replaced_by.
        new_raw = secrets.token_urlsafe(48)
        new_record = RefreshToken(
            id=uuid.uuid4(),
            user_id=user.id,
            token_hash=_hash_refresh_token(new_raw),
            expires_at=utc_now() + timedelta(days=self.settings.REFRESH_TOKEN_EXPIRE_DAYS),
            revoked_at=None,
            replaced_by=None,
        )
        self.db.add(new_record)
        self.db.flush()
        record.revoked_at = now
        record.replaced_by = new_record.id
        self.db.commit()

        access = self.create_access_token({"sub": str(user.id), "role": user.role})
        return TokenPair(
            access_token=access,
            refresh_token=new_raw,
            expires_in=self._access_expires_in_seconds(),
        )

    def logout(self, refresh_token: str) -> None:
        """Revoke a single refresh token (idempotent)."""
        if not refresh_token or not refresh_token.strip():
            return
        token_hash = _hash_refresh_token(refresh_token.strip())
        record = (
            self.db.query(RefreshToken)
            .filter(RefreshToken.token_hash == token_hash)
            .first()
        )
        if record is None or record.revoked_at is not None:
            return
        record.revoked_at = utc_now()
        self.db.commit()

    def revoke_all_user_tokens(self, user_id: uuid.UUID) -> None:
        """Revoke every active refresh token for a user."""
        now = utc_now()
        (
            self.db.query(RefreshToken)
            .filter(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .update({"revoked_at": now}, synchronize_session=False)
        )
        self.db.commit()

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
