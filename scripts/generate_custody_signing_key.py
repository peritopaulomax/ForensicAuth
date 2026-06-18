#!/usr/bin/env python3
"""Generate Ed25519 key pair for custody signing (store private key outside git)."""

import base64
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[1]
SECRETS = ROOT / "secrets"
SECRETS.mkdir(exist_ok=True)

private_key = Ed25519PrivateKey.generate()
private_bytes = private_key.private_bytes(
    encoding=serialization.Encoding.Raw,
    format=serialization.PrivateFormat.Raw,
    encryption_algorithm=serialization.NoEncryption(),
)
public_pem = private_key.public_key().public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo,
).decode()

private_b64 = base64.b64encode(private_bytes).decode()
pem_path = SECRETS / "custody_ed25519_private.pem"
pub_path = SECRETS / "custody_ed25519_public.pem"

pem_path.write_text(
    private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode(),
    encoding="utf-8",
)
pub_path.write_text(public_pem, encoding="utf-8")

print("Chaves geradas em secrets/ (nao versionar).")
print("Adicione ao .env:")
print(f"CUSTODY_SIGNING_KEY_ID=forensicauth-ed25519-v1")
print(f"CUSTODY_SIGNING_PRIVATE_KEY={private_b64}")
print("Ou use o PEM em secrets/custody_ed25519_private.pem")
