"""Startup warmup for IAPL checkpoints."""

from __future__ import annotations

import logging
import os
import threading

from core.legacy.iapl.iapl_pipeline import iapl_model_cache_keys, warm_iapl_models

logger = logging.getLogger(__name__)

_warmup_lock = threading.Lock()
_warmup_thread: threading.Thread | None = None
_warmup_state: dict = {"status": "idle", "variants": [], "error": None}


def iapl_warmup_status() -> dict:
    with _warmup_lock:
        return {**_warmup_state, "cache_keys": iapl_model_cache_keys()}


def _warmup_worker() -> None:
    with _warmup_lock:
        _warmup_state["status"] = "running"
        _warmup_state["error"] = None
    try:
        loaded = warm_iapl_models()
        with _warmup_lock:
            _warmup_state["status"] = "ready" if loaded else "skipped"
            _warmup_state["variants"] = loaded
        if loaded:
            logger.info("IAPL warmup concluido: %s", ", ".join(loaded))
    except Exception as exc:
        with _warmup_lock:
            _warmup_state["status"] = "error"
            _warmup_state["error"] = str(exc)
        logger.exception("IAPL warmup falhou: %s", exc)


def schedule_iapl_warmup() -> threading.Thread | None:
    global _warmup_thread

    # Desligado por padrao: warmup IAPL compete com Effort/SAFE por ~3 GB VRAM (CLIP ViT-L).
    if os.environ.get("IAPL_WARMUP_ON_STARTUP", "").lower() not in {"1", "true", "yes"}:
        with _warmup_lock:
            _warmup_state["status"] = "disabled"
        return None

    with _warmup_lock:
        if _warmup_thread is not None and _warmup_thread.is_alive():
            return _warmup_thread
        _warmup_state["status"] = "scheduled"
        _warmup_thread = threading.Thread(target=_warmup_worker, name="iapl-warmup", daemon=True)
        _warmup_thread.start()
        return _warmup_thread
