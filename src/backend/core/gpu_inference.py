"""CUDA/CPU device resolution and GPU memory lifecycle for ML inference."""

from __future__ import annotations

import gc
import logging
import threading
from contextlib import contextmanager
from typing import Any, Callable, TypeVar

T = TypeVar("T")

logger = logging.getLogger(__name__)

ML_GPU_TECHNIQUES = frozenset(
    {
        "synthetic_image_detection",
        "deepfake_similarity",
        "safire",
        "noiseprint",
        "imdlbenco",
        "videofact",
        "stil_video_detection",
        "lowres_fake_video",
        "distildire",
    }
)

_ml_gpu_job_lock = threading.Lock()
_last_gpu_fallback_reason: str | None = None


def resolve_inference_device(*, prefer_cuda: bool = True):
    """Prefer CUDA when available; otherwise CPU."""
    import torch

    if prefer_cuda and torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def uses_cpu(device) -> bool:
    return device.type == "cpu"


def device_display_label(device_or_type: Any) -> str:
    """Rótulo curto para UI/relatório: GPU ou CPU."""
    if hasattr(device_or_type, "type"):
        label = device_or_type.type
    else:
        label = str(device_or_type).lower()
    return "GPU" if label == "cuda" else "CPU"


def cuda_memory_snapshot() -> dict[str, int | None]:
    """Return free/total VRAM in MiB when CUDA is available."""
    import torch

    if not torch.cuda.is_available():
        return {"free_mb": None, "total_mb": None, "allocated_mb": None}
    free, total = torch.cuda.mem_get_info()
    return {
        "free_mb": free // (1024 * 1024),
        "total_mb": total // (1024 * 1024),
        "allocated_mb": torch.cuda.memory_allocated() // (1024 * 1024),
    }


def is_cuda_oom_or_device_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    if "should be the same" in msg:
        return False
    return any(
        token in msg
        for token in (
            "cuda",
            "cublas",
            "cudnn",
            "out of memory",
            "no kernel image",
            "device-side assert",
            "not compiled with cuda",
        )
    )


def release_gpu_memory(*objects: Any) -> None:
    """Move tensors/modules to CPU, collect garbage and free CUDA cache."""
    import torch

    for obj in objects:
        if obj is None:
            continue
        try:
            levels = getattr(obj, "level", None)
            if levels:
                for idx, tensor in enumerate(levels):
                    if tensor is not None:
                        levels[idx] = None
        except Exception:
            pass
        try:
            cpu_fn = getattr(obj, "cpu", None)
            if callable(cpu_fn):
                cpu_fn()
        except Exception:
            pass

    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        try:
            torch.cuda.ipc_collect()
        except Exception:
            pass


def pop_gpu_fallback_reason() -> str | None:
    """Return and clear the reason for the most recent GPU→CPU fallback."""
    global _last_gpu_fallback_reason
    reason = _last_gpu_fallback_reason
    _last_gpu_fallback_reason = None
    return reason


@contextmanager
def ml_gpu_job_slot(technique: str):
    """Serialize GPU-heavy jobs so concurrent threads do not OOM or thrash CPU."""
    if technique in ML_GPU_TECHNIQUES:
        with _ml_gpu_job_lock:
            yield
    else:
        yield


def prepare_vram_for_iapl(*, log: bool = True) -> dict[str, dict[str, int | None]]:
    """Libera VRAM de modelos ja inferidos antes do IAPL (CLIP ViT-L + TTA batch 32)."""
    snap_before = cuda_memory_snapshot()
    try:
        from core.legacy.effort.effort_pipeline import clear_effort_model_cache

        clear_effort_model_cache()
    except Exception:
        pass

    try:
        from core.legacy.safe.safe_pipeline import clear_safe_model_cache

        clear_safe_model_cache()
    except Exception:
        pass

    try:
        from core.legacy.camo.camo_pipeline import clear_camo_model_cache

        clear_camo_model_cache()
    except Exception:
        pass

    try:
        from core.legacy.iapl.iapl_pipeline import clear_iapl_model_cache

        clear_iapl_model_cache()
    except Exception:
        pass

    try:
        from core.legacy.synthetic_image_detection.pipeline import release_gpu_memory

        release_gpu_memory()
    except Exception:
        pass

    release_gpu_memory()
    snap_after = cuda_memory_snapshot()
    if log:
        logger.info(
            "VRAM preparada para IAPL — livre: %s MiB → %s MiB (total %s MiB)",
            snap_before.get("free_mb"),
            snap_after.get("free_mb"),
            snap_after.get("total_mb"),
        )
    return {"before": snap_before, "after": snap_after}


def purge_foreign_gpu_model_caches(*, include_trufor: bool = True) -> None:
    """Release VRAM from other ML plugins before heavy full-res inference."""
    try:
        from core.legacy.safire.safire_pipeline import clear_predictor_cache

        clear_predictor_cache()
    except Exception:
        pass

    try:
        from core.legacy.imdlbenco import imdlbenco_pipeline as imdl_pipeline

        imdl_pipeline._clear_gpu_model_cache()
    except Exception:
        pass

    try:
        from core.legacy.iml_vit import iml_vit_pipeline as iml_vit

        evict_cache_keys_on_device(iml_vit._model_cache)
        iml_vit._model_cache.clear()
    except Exception:
        pass

    try:
        from core.legacy.synthetic_image_detection.pipeline import release_gpu_memory

        release_gpu_memory()
    except Exception:
        pass

    try:
        from core.legacy.distildire.distildire_pipeline import clear_distildire_model_cache

        clear_distildire_model_cache()
    except Exception:
        pass

    if include_trufor:
        try:
            from core.legacy.imdlbenco import trufor_official_pipeline as trufor

            evict_cache_keys_on_device(getattr(trufor._load_model, "_cache", {}))
        except Exception:
            pass

    release_gpu_memory()


def run_with_device_fallback(
    run_fn: Callable[[Any], T],
    *,
    on_fallback: Callable[[], None] | None = None,
    on_before_cpu_fallback: Callable[[str], None] | None = None,
    allow_cpu_fallback: bool = True,
) -> tuple[T, Any]:
    """Run inference on CUDA first; retry on CPU after CUDA/OOM failures."""
    import torch

    global _last_gpu_fallback_reason
    _last_gpu_fallback_reason = None

    device = resolve_inference_device()
    try:
        return run_fn(device), device
    except RuntimeError as exc:
        if device.type != "cuda" or not is_cuda_oom_or_device_error(exc):
            raise
        _last_gpu_fallback_reason = str(exc)
        logger.warning("GPU inference failed; falling back to CPU: %s", exc)
        if not allow_cpu_fallback:
            purge_foreign_gpu_model_caches(include_trufor=True)
            raise RuntimeError(
                "VRAM insuficiente para TruFor full-res na GPU. "
                "Aguarde outros jobs ML terminarem ou reinicie o backend para liberar a GPU. "
                f"Detalhe CUDA: {exc}"
            ) from exc
        if on_before_cpu_fallback is not None:
            on_before_cpu_fallback(str(exc))
        purge_foreign_gpu_model_caches(include_trufor=True)
        if on_fallback is not None:
            on_fallback()
        device = torch.device("cpu")
        return run_fn(device), device
    finally:
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()


def evict_cache_keys_on_device(cache: dict, device_label: str = "cuda") -> None:
    """Remove cache entries tied to a device label and release their GPU memory."""
    keys = [key for key in list(cache.keys()) if f":{device_label}" in str(key)]
    for key in keys:
        release_gpu_memory(cache.pop(key, None))
    release_gpu_memory()
