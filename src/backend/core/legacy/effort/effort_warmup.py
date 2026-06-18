"""Startup warmup for Effort (CLIP ViT-L/14 + checkpoints) — keeps models resident."""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field
from typing import Any

import torch

from core.gpu_inference import resolve_inference_device
from core.legacy.effort.effort_pipeline import (
    _load_model,
    effort_model_cache_keys,
)
from core.legacy.effort.effort_runtime import EFFORT_VARIANTS, effort_runtime_status

logger = logging.getLogger(__name__)

_warmup_lock = threading.Lock()
_warmup_thread: threading.Thread | None = None
_warmup_state: dict[str, Any] = {
    "status": "idle",
    "device": None,
    "variants": {},
    "error": None,
}


@dataclass
class EffortWarmupResult:
    device: str
    loaded_variants: list[str] = field(default_factory=list)
    skipped_variants: dict[str, str] = field(default_factory=dict)
    cache_keys: list[str] = field(default_factory=list)


def effort_warmup_status() -> dict[str, Any]:
    with _warmup_lock:
        return dict(_warmup_state)


def _dummy_forward(model: Any, device: torch.device) -> None:
    tensor = torch.zeros(1, 3, 224, 224, device=device)
    data = {"image": tensor, "label": torch.tensor([0], device=device)}
    with torch.no_grad():
        model(data, inference=True)


def warm_effort_models(
    *,
    variants: list[str] | None = None,
    device: torch.device | None = None,
) -> EffortWarmupResult:
    """Load ready Effort variants into the process cache and run a dummy forward."""
    from app.config import get_settings

    settings = get_settings()
    if settings.EFFORT_WARMUP_VARIANTS.strip():
        configured = [
            v.strip()
            for v in settings.EFFORT_WARMUP_VARIANTS.split(",")
            if v.strip()
        ]
    else:
        configured = list(EFFORT_VARIANTS.keys())
    target_device = device or resolve_inference_device()
    variant_ids = variants or configured
    loaded: list[str] = []
    skipped: dict[str, str] = {}

    for variant_id in variant_ids:
        ok, reason = effort_runtime_status(variant=variant_id)
        if not ok:
            skipped[variant_id] = reason
            continue
        try:
            model = _load_model(variant_id, target_device)
            _dummy_forward(model, target_device)
            loaded.append(variant_id)
            logger.info(
                "Effort warmup: variante %s carregada em %s",
                variant_id,
                target_device.type,
            )
        except Exception as exc:
            skipped[variant_id] = str(exc)
            logger.warning("Effort warmup falhou para %s: %s", variant_id, exc)

    return EffortWarmupResult(
        device=target_device.type,
        loaded_variants=loaded,
        skipped_variants=skipped,
        cache_keys=effort_model_cache_keys(),
    )


def _warmup_worker() -> None:
    with _warmup_lock:
        _warmup_state["status"] = "running"
        _warmup_state["error"] = None

    try:
        result = warm_effort_models()
        with _warmup_lock:
            _warmup_state["status"] = "ready" if result.loaded_variants else "skipped"
            _warmup_state["device"] = result.device
            _warmup_state["variants"] = {
                variant: "loaded" for variant in result.loaded_variants
            }
            _warmup_state["variants"].update(
                {variant: f"skipped: {reason}" for variant, reason in result.skipped_variants.items()}
            )
            if result.loaded_variants:
                logger.info(
                    "Effort warmup concluido (%s): %s",
                    result.device,
                    ", ".join(result.loaded_variants),
                )
            else:
                logger.info("Effort warmup ignorado — nenhuma variante pronta")
    except Exception as exc:
        with _warmup_lock:
            _warmup_state["status"] = "error"
            _warmup_state["error"] = str(exc)
        logger.exception("Effort warmup falhou: %s", exc)


def schedule_effort_warmup() -> threading.Thread | None:
    """Start Effort warmup in a background daemon thread (idempotent)."""
    global _warmup_thread

    if os.environ.get("EFFORT_WARMUP_ON_STARTUP", "").lower() in {"0", "false", "no"}:
        with _warmup_lock:
            _warmup_state["status"] = "disabled"
        logger.info("Effort warmup desabilitado via EFFORT_WARMUP_ON_STARTUP")
        return None

    try:
        from app.config import get_settings

        if not get_settings().EFFORT_WARMUP_ON_STARTUP:
            with _warmup_lock:
                _warmup_state["status"] = "disabled"
            logger.info("Effort warmup desabilitado nas configuracoes")
            return None
    except Exception:
        pass

    with _warmup_lock:
        if _warmup_thread is not None and _warmup_thread.is_alive():
            return _warmup_thread
        _warmup_state["status"] = "scheduled"
        _warmup_thread = threading.Thread(
            target=_warmup_worker,
            name="effort-warmup",
            daemon=True,
        )
        _warmup_thread.start()
        return _warmup_thread
