"""Startup warmup for CAMO (BitMind UCF MoE)."""

from __future__ import annotations

import logging
import os
import threading

from core.legacy.camo.camo_pipeline import camo_model_cache_keys, warm_camo_model

logger = logging.getLogger(__name__)

_warmup_lock = threading.Lock()
_warmup_thread: threading.Thread | None = None
_warmup_state: dict = {"status": "idle", "ready": False, "error": None}


def camo_warmup_status() -> dict:
    with _warmup_lock:
        return {**_warmup_state, "cache_keys": camo_model_cache_keys()}


def _warmup_worker() -> None:
    with _warmup_lock:
        _warmup_state["status"] = "running"
        _warmup_state["error"] = None
    try:
        ready = warm_camo_model()
        with _warmup_lock:
            _warmup_state["status"] = "ready" if ready else "skipped"
            _warmup_state["ready"] = ready
        if ready:
            logger.info("CAMO warmup concluido")
    except Exception as exc:
        with _warmup_lock:
            _warmup_state["status"] = "error"
            _warmup_state["error"] = str(exc)
        logger.exception("CAMO warmup falhou: %s", exc)


def schedule_camo_warmup() -> threading.Thread | None:
    global _warmup_thread

    if os.environ.get("CAMO_WARMUP_ON_STARTUP", "").lower() not in {"1", "true", "yes"}:
        with _warmup_lock:
            _warmup_state["status"] = "disabled"
        return None

    with _warmup_lock:
        if _warmup_thread is not None and _warmup_thread.is_alive():
            return _warmup_thread
        _warmup_state["status"] = "scheduled"
        _warmup_thread = threading.Thread(target=_warmup_worker, name="camo-warmup", daemon=True)
        _warmup_thread.start()
        return _warmup_thread
