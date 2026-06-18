"""Distributed GPU lock via Redis — serializes ML jobs across processes."""

from __future__ import annotations

import logging
import socket
import time
import uuid
from contextlib import contextmanager
from typing import Iterator

logger = logging.getLogger(__name__)


def _settings():
    from app.config import get_settings

    return get_settings()


def _redis_client():
    import redis

    settings = _settings()
    return redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)


def worker_lock_id() -> str:
    settings = _settings()
    queue = settings.FORENSICAUTH_WORKER_QUEUE or settings.FORENSICAUTH_PROCESS_ROLE
    host = socket.gethostname()
    return f"{queue}@{host}:{uuid.uuid4().hex[:8]}"


@contextmanager
def gpu_distributed_lock(*, blocking: bool = True, poll_seconds: float = 2.0) -> Iterator[bool]:
    """Acquire global GPU lock when GPU_DISTRIBUTED_LOCK is enabled."""
    settings = _settings()
    if not settings.GPU_DISTRIBUTED_LOCK:
        yield True
        return

    key = settings.GPU_LOCK_KEY
    ttl = int(settings.GPU_LOCK_TTL_SECONDS)
    token = worker_lock_id()
    client = _redis_client()
    acquired = False

    try:
        if blocking:
            deadline = time.monotonic() + max(ttl, 300)
            while time.monotonic() < deadline:
                if client.set(key, token, nx=True, ex=ttl):
                    acquired = True
                    break
                time.sleep(poll_seconds)
        else:
            acquired = bool(client.set(key, token, nx=True, ex=ttl))

        if acquired:
            logger.debug("GPU lock adquirido (%s)", token)
        else:
            logger.warning("GPU lock indisponivel (%s)", key)

        yield acquired
    finally:
        if acquired:
            try:
                current = client.get(key)
                if current == token:
                    client.delete(key)
            except Exception:
                logger.exception("Falha ao liberar GPU lock")
