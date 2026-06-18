"""Helpers for custody chain hashing."""

import hashlib
import json
from typing import Any, Dict


def hash_canonical_json(data: Dict[str, Any]) -> str:
    """SHA-256 of JSON with sorted keys (reproducible parameter fingerprint)."""
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
