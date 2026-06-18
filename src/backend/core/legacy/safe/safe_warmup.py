"""Startup warmup for SAFE — keeps model resident in process cache."""

from __future__ import annotations

import logging
import threading

from core.legacy.safe.safe_pipeline import safe_model_cache_keys, warm_safe_model

logger = logging.getLogger(__name__)

_warmup_lock = threading.Lock()
_warmup_thread: threading.Thread | None = None
_warmup_state = {"status": "idle", "loaded": False, "error": None}


def safe_warmup_status() -> dict:
    with _warmup_lock:
        return {
            **_warmup_state,
            "cache_keys": safe_model_cache_keys(),
        }


def _warmup_worker() -> None:
    with _warmup_lock:
        _warmup_state["status"] = "running"
        _warmup_state["error"] = None
    try:
        loaded = warm_safe_model()
        with _warmup_lock:
            _warmup_state["status"] = "ready" if loaded else "skipped"
            _warmup_state["loaded"] = loaded
        if loaded:
            logger.info("SAFE warmup concluido")
        else:
            logger.info("SAFE warmup ignorado — pesos ou dependencias ausentes")
    except Exception as exc:
        with _warmup_lock:
            _warmup_state["status"] = "error"
            _warmup_state["error"] = str(exc)
        logger.exception("SAFE warmup falhou: %s", exc)


def schedule_safe_warmup() -> threading.Thread | None:
    global _warmup_thread
    import os

    if os.environ.get("SAFE_WARMUP_ON_STARTUP", "").lower() in {"0", "false", "no"}:
        with _warmup_lock:
            _warmup_state["status"] = "disabled"
        return None

    with _warmup_lock:
        if _warmup_thread is not None and _warmup_thread.is_alive():
            return _warmup_thread
        _warmup_state["status"] = "scheduled"
        _warmup_thread = threading.Thread(target=_warmup_worker, name="safe-warmup", daemon=True)
        _warmup_thread.start()
        return _warmup_thread
