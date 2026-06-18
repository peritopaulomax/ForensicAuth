"""VRAM residency policy — resident baseline, LRU, conditional purge."""

from __future__ import annotations

import logging
import time
from typing import Iterable

logger = logging.getLogger(__name__)

_LRU_LAST_USED: dict[str, float] = {}

# Techniques that always purge foreign caches before running (exclusive / heavy).
_EXCLUSIVE_TECHNIQUES = frozenset(
    {
        "imdlbenco",  # TruFor full-res path uses purge in pipeline
    }
)

_TECHNIQUE_ALIASES: dict[str, str] = {
    "synthetic_image_detection": "synthetic",
    "audio_spectrogram": "audio",
}


def _settings():
    from app.config import get_settings

    return get_settings()


def _normalize_technique(technique: str) -> str:
    return _TECHNIQUE_ALIASES.get(technique, technique.split("_")[0] if technique else "")


def resident_technique_ids() -> set[str]:
    raw = _settings().GPU_RESIDENT_TECHNIQUES or ""
    return {part.strip().lower() for part in raw.split(",") if part.strip()}


def should_keep_resident(technique: str) -> bool:
    if technique == "synthetic_image_detection":
        return bool(_settings().SYNTHETIC_KEEP_RESIDENT)
    key = _normalize_technique(technique)
    return key in resident_technique_ids()


def is_exclusive_technique(technique: str) -> bool:
    return technique in _EXCLUSIVE_TECHNIQUES


def vram_pressure_threshold_mb() -> int:
    s = _settings()
    return int(s.GPU_MIN_FREE_MB) + int(s.GPU_RESERVED_FUTURE_MB)


def vram_under_pressure() -> bool:
    from core.gpu_inference import cuda_memory_snapshot

    snap = cuda_memory_snapshot()
    free_mb = snap.get("free_mb")
    if free_mb is None:
        return False
    return int(free_mb) < vram_pressure_threshold_mb()


def touch_lru(technique: str) -> None:
    key = _normalize_technique(technique)
    if key:
        _LRU_LAST_USED[key] = time.monotonic()


def lru_expired(technique: str) -> bool:
    key = _normalize_technique(technique)
    last = _LRU_LAST_USED.get(key)
    if last is None:
        return True
    ttl = _settings().GPU_LRU_TTL_SECONDS
    return (time.monotonic() - last) > ttl


def maybe_evict_for_job(technique: str) -> None:
    """Purge foreign GPU caches only when VRAM is tight or job is exclusive."""
    if should_keep_resident(technique) and not is_exclusive_technique(technique):
        if not vram_under_pressure():
            return
    from core.gpu_inference import purge_foreign_gpu_model_caches

    logger.info("VRAM sob pressao ou job exclusivo — liberando caches estrangeiros (tecnica=%s)", technique)
    purge_foreign_gpu_model_caches(include_trufor=True)


def prepare_vram_for_iapl_if_needed() -> dict:
    """Clear baseline caches for IAPL only when free VRAM is below threshold."""
    from core.gpu_inference import cuda_memory_snapshot, prepare_vram_for_iapl

    if not vram_under_pressure():
        snap = cuda_memory_snapshot()
        logger.info(
            "IAPL: VRAM suficiente (livre %s MiB) — mantendo caches residentes",
            snap.get("free_mb"),
        )
        return {"before": snap, "after": snap, "skipped": True}
    return prepare_vram_for_iapl()


def release_synthetic_if_not_resident() -> None:
    if should_keep_resident("synthetic_image_detection"):
        return
    try:
        from core.legacy.synthetic_image_detection.pipeline import release_gpu_memory

        release_gpu_memory()
    except Exception:
        pass


def release_imdl_cache_if_needed() -> None:
    if should_keep_resident("imdlbenco") and not lru_expired("imdlbenco"):
        touch_lru("imdlbenco")
        return
    try:
        from core.legacy.imdlbenco import imdlbenco_pipeline as pipeline

        pipeline._clear_gpu_model_cache()
    except Exception:
        pass


def release_safire_cache_if_needed() -> None:
    if should_keep_resident("safire") and not lru_expired("safire"):
        touch_lru("safire")
        return
    try:
        from core.legacy.safire.safire_pipeline import clear_predictor_cache

        clear_predictor_cache()
    except Exception:
        pass


def clear_lru_for_techniques(techniques: Iterable[str]) -> None:
    for technique in techniques:
        _LRU_LAST_USED.pop(_normalize_technique(technique), None)
