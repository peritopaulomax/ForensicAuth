"""Ed25519 signing for custody records and case closure manifests."""

from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Optional

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from app.config import Settings, get_settings

_DEV_PRIVATE_KEY: Ed25519PrivateKey | None = None
_DEV_PUBLIC_KEY: Ed25519PublicKey | None = None


def dev_signing_key_path(settings: Settings) -> Path:
    """Chave Ed25519 de desenvolvimento — mesma entre reinicios do backend.

    Em producao use CUSTODY_SIGNING_PRIVATE_KEY no .env. Se a chave mudar,
    assinaturas antigas deixam de conferir (comportamento correto); nao re-assine
    automaticamente — investigue rotacao de chave ou adulteracao.
    """
    return Path(settings.UPLOAD_DIR).resolve().parent / ".data" / "custody_ed25519_dev.key"


def _load_or_create_dev_key(settings: Settings) -> tuple[Ed25519PrivateKey, Ed25519PublicKey]:
    global _DEV_PRIVATE_KEY, _DEV_PUBLIC_KEY
    if _DEV_PRIVATE_KEY is not None and _DEV_PUBLIC_KEY is not None:
        return _DEV_PRIVATE_KEY, _DEV_PUBLIC_KEY

    path = dev_signing_key_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.is_file():
        raw = path.read_text(encoding="ascii").strip()
        private = _decode_private_key(raw)
    else:
        private = Ed25519PrivateKey.generate()
        raw_bytes = private.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )
        path.write_text(base64.b64encode(raw_bytes).decode("ascii"), encoding="ascii")
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass

    _DEV_PRIVATE_KEY = private
    _DEV_PUBLIC_KEY = private.public_key()
    return _DEV_PRIVATE_KEY, _DEV_PUBLIC_KEY


def _decode_private_key(raw: str) -> Ed25519PrivateKey:
    raw = raw.strip()
    if "BEGIN" in raw:
        key = serialization.load_pem_private_key(raw.encode(), password=None)
        if not isinstance(key, Ed25519PrivateKey):
            raise ValueError("Chave privada deve ser Ed25519")
        return key
    padded = raw + "=" * (-len(raw) % 4)
    key_bytes = base64.b64decode(padded)
    if len(key_bytes) == 32:
        return Ed25519PrivateKey.from_private_bytes(key_bytes)
    if len(key_bytes) == 64:
        return Ed25519PrivateKey.from_private_bytes(key_bytes[:32])
    raise ValueError("Formato de chave privada invalido")


def _decode_public_key(raw: str) -> Ed25519PublicKey:
    raw = raw.strip()
    if "BEGIN" in raw:
        key = serialization.load_pem_public_key(raw.encode())
        if not isinstance(key, Ed25519PublicKey):
            raise ValueError("Chave publica deve ser Ed25519")
        return key
    padded = raw + "=" * (-len(raw) % 4)
    key_bytes = base64.b64decode(padded)
    if len(key_bytes) == 32:
        return Ed25519PublicKey.from_public_bytes(key_bytes)
    raise ValueError("Formato de chave publica invalido")


class CustodySigningService:
    """Sign and verify SHA-256 hex digests with Ed25519."""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self.key_id = self.settings.CUSTODY_SIGNING_KEY_ID

    def _private_key(self) -> Ed25519PrivateKey:
        if self.settings.CUSTODY_SIGNING_PRIVATE_KEY:
            return _decode_private_key(self.settings.CUSTODY_SIGNING_PRIVATE_KEY)
        return _load_or_create_dev_key(self.settings)[0]

    def _public_key(self) -> Ed25519PublicKey:
        if self.settings.CUSTODY_SIGNING_PUBLIC_KEY:
            return _decode_public_key(self.settings.CUSTODY_SIGNING_PUBLIC_KEY)
        return _load_or_create_dev_key(self.settings)[1]

    def sign_digest_hex(self, digest_hex: str) -> dict[str, str]:
        """Sign a 64-char SHA-256 hex string."""
        signature = self._private_key().sign(digest_hex.encode("utf-8"))
        return {
            "signature_b64": base64.b64encode(signature).decode("ascii"),
            "signing_key_id": self.key_id,
        }

    def verify_digest_hex(
        self,
        digest_hex: str,
        signature_b64: str | None,
        signing_key_id: str | None = None,
    ) -> bool:
        if not signature_b64:
            return False
        if signing_key_id and signing_key_id != self.key_id:
            return False
        try:
            sig = base64.b64decode(signature_b64)
            self._public_key().verify(sig, digest_hex.encode("utf-8"))
            return True
        except Exception:
            return False

    def public_key_pem(self) -> str:
        return (
            self._public_key()
            .public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            .decode("ascii")
        )
