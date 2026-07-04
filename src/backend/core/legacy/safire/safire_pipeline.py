"""SAFIRE inference pipeline (binary localization + multi-source partitioning)."""

from __future__ import annotations

import sys
import types
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from importlib.machinery import ModuleSpec
from pathlib import Path
from typing import Any, Callable, Literal

import cv2
import numpy as np
from PIL import Image

from core.gpu_inference import (
    evict_cache_keys_on_device,
    release_gpu_memory,
    run_with_device_fallback,
    uses_cpu,
)
from core.legacy.safire.safire_runtime import (
    SAM_CHECKPOINT,
    SAFIRE_CHECKPOINT,
    resolve_safire_models_dir,
    safire_repo_dir,
)

ProgressFn = Callable[[int, str], None] | None

MULTI_COLOR_MAP = {
    0: (190, 174, 212),
    1: (127, 201, 127),
    2: (253, 192, 134),
    3: (255, 255, 153),
    4: (251, 128, 114),
    5: (128, 177, 211),
    6: (179, 222, 105),
    7: (255, 255, 255),
}


@dataclass
class SafireAnalysisResult:
    mode: str
    input_image: Image.Image
    heatmap_image: Image.Image
    overlay_image: Image.Image
    multi_segment_image: Image.Image | None
    original_size: tuple[int, int]
    inference_size: tuple[int, int]
    cluster_type: str | None
    cluster_count: int | None
    mean_forgery_score: float | None
    inference_device: str
    gpu_fallback_reason: str | None = None
    gpu_fallback_warning: str | None = None
    points_per_side_effective: int = 16
    points_per_batch_effective: int = 256


_predictor_cache: dict[str, Any] = {}

_SAFIRE_VENDOR_MODULE_PREFIXES = (
    "networks",
    "segment_anything",
    "safire_kmeans",
)


def _install_safire_networks_package(root: str) -> None:
    networks_dir = Path(root) / "networks"
    if not networks_dir.is_dir():
        return

    module = types.ModuleType("networks")
    module.__file__ = None
    module.__package__ = "networks"
    module.__path__ = [str(networks_dir)]  # type: ignore[attr-defined]
    spec = ModuleSpec("networks", loader=None, is_package=True)
    spec.submodule_search_locations = [str(networks_dir)]
    module.__spec__ = spec
    sys.modules["networks"] = module


@contextmanager
def _safire_vendor_context():
    """Temporarily isolate SAFIRE's vendor imports from other ML repos.

    Several bundled detectors use top-level package names such as ``networks``.
    A long-lived worker may already have one of those packages loaded, so SAFIRE
    must import its official modules with a clean namespace.
    """
    root = str(safire_repo_dir())
    inserted = root not in sys.path
    saved = {
        key: value
        for key, value in sys.modules.items()
        if key in _SAFIRE_VENDOR_MODULE_PREFIXES
        or any(key.startswith(f"{prefix}.") for prefix in _SAFIRE_VENDOR_MODULE_PREFIXES)
    }
    for key in list(saved):
        sys.modules.pop(key, None)
    if inserted:
        sys.path.insert(0, root)
    _install_safire_networks_package(root)
    try:
        yield
    finally:
        for key in list(sys.modules):
            if key in _SAFIRE_VENDOR_MODULE_PREFIXES or any(
                key.startswith(f"{prefix}.") for prefix in _SAFIRE_VENDOR_MODULE_PREFIXES
            ):
                sys.modules.pop(key, None)
        sys.modules.update(saved)
        if inserted:
            with suppress(ValueError):
                sys.path.remove(root)


def _report(on_progress: ProgressFn, pct: int, label: str) -> None:
    if on_progress:
        on_progress(pct, label)


def _default_points_per_side(requested: int, device) -> int:
    """Official infer_*.py uses points_per_side=16 on all devices."""
    return requested


def _default_points_per_batch(requested: int, device) -> int:
    if uses_cpu(device):
        return min(requested, 64)
    return requested


def _prepare_gpu_for_safire() -> None:
    from core.gpu_inference import purge_foreign_gpu_model_caches

    purge_foreign_gpu_model_caches(include_trufor=True)


def _seed_safire_multi() -> None:
    """Match bundled ForensicsEval/outputs_multi reference (k-means init)."""
    import random

    import torch

    random.seed(31)
    np.random.seed(31)
    torch.manual_seed(31)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(31)


def clear_predictor_cache() -> None:
    evict_cache_keys_on_device(_predictor_cache)
    _predictor_cache.clear()
    release_gpu_memory()


def _load_rgb_arrays(evidence_path: str) -> tuple[np.ndarray, np.ndarray, tuple[int, int]]:
    img = Image.open(evidence_path).convert("RGB")
    original = np.array(img, dtype=np.uint8)
    h, w = original.shape[:2]
    resized = cv2.resize(original, (1024, 1024), interpolation=cv2.INTER_LINEAR)
    return resized, original, (h, w)


def _resize_map_to_original(
    pred: np.ndarray,
    original_size: tuple[int, int],
    *,
    nearest: bool = False,
) -> np.ndarray:
    h, w = original_size
    interp = cv2.INTER_NEAREST if nearest else cv2.INTER_LINEAR
    if pred.ndim == 3:
        out = np.zeros((h, w, pred.shape[2]), dtype=pred.dtype)
        for c in range(pred.shape[2]):
            out[..., c] = cv2.resize(pred[..., c], (w, h), interpolation=interp)
        return out
    return cv2.resize(pred, (w, h), interpolation=interp)


def _resize_pil_to_original(img: Image.Image, original_size: tuple[int, int], *, nearest: bool = True) -> Image.Image:
    h, w = original_size
    if img.size == (w, h):
        return img
    resample = Image.Resampling.NEAREST if nearest else Image.Resampling.BILINEAR
    return img.resize((w, h), resample=resample)


def _heatmap_to_pil(heatmap: np.ndarray) -> Image.Image:
    arr = np.clip(heatmap * 255.0, 0, 255).astype(np.uint8)
    return Image.fromarray(arr, mode="L")


def _overlay_heatmap(original: np.ndarray, heatmap: np.ndarray, alpha: float = 0.45) -> Image.Image:
    import matplotlib.cm as cm

    colored = (cm.inferno(np.clip(heatmap, 0.0, 1.0))[..., :3] * 255).astype(np.uint8)
    base = original.astype(np.float32)
    over = colored.astype(np.float32)
    blended = (base * (1.0 - alpha) + over * alpha).astype(np.uint8)
    return Image.fromarray(blended, mode="RGB")


def _multi_logits_to_rgb(logits: np.ndarray) -> Image.Image:
    pred_np = np.argmax(logits, axis=0)
    color_array = np.zeros((pred_np.shape[0], pred_np.shape[1], 3), dtype=np.uint8)
    for key, value in MULTI_COLOR_MAP.items():
        color_array[pred_np == key] = value
    return Image.fromarray(color_array, mode="RGB")


def _get_predictor(
    mode: Literal["binary", "multi"],
    points_per_side: int,
    points_per_batch: int,
    on_progress: ProgressFn,
    *,
    device,
):
    cache_key = f"{mode}:{points_per_side}:{points_per_batch}:{device.type}"
    if cache_key in _predictor_cache:
        return _predictor_cache[cache_key]

    models_dir = resolve_safire_models_dir()
    if models_dir is None:
        raise RuntimeError("Pesos SAFIRE nao encontrados")

    safire_ckpt = models_dir / SAFIRE_CHECKPOINT
    sam_ckpt = models_dir / SAM_CHECKPOINT

    label = "GPU" if device.type == "cuda" else "CPU (lento)"
    _report(on_progress, 12, f"Carregando SAM + SAFIRE em {label}")
    import torch

    with _safire_vendor_context():
        from segment_anything import sam_model_registry
        from networks.safire_model import AdaptorSAM

        sam_model = sam_model_registry["vit_b_adaptor"](checkpoint=str(sam_ckpt))
        safire_model = AdaptorSAM(
            image_encoder=sam_model.image_encoder,
            mask_decoder=sam_model.mask_decoder,
            prompt_encoder=sam_model.prompt_encoder,
        ).to(device)

        try:
            checkpoint = torch.load(str(safire_ckpt), map_location=device, weights_only=False)
        except TypeError:
            checkpoint = torch.load(str(safire_ckpt), map_location=device)
        safire_model.load_state_dict(
            {k.replace("module.", ""): v for k, v in checkpoint["model"].items()}
        )
        safire_model.eval()

        if mode == "binary":
            from networks.safire_predictor_binary import SafirePredictor
        else:
            from networks.safire_predictor_multi import SafirePredictor

        predictor = SafirePredictor(
            safire_model,
            points_per_side=points_per_side,
            points_per_batch=points_per_batch,
            pred_iou_thresh=0,
            stability_score_thresh=0.0,
            box_nms_thresh=0.0,
        )
    _predictor_cache[cache_key] = predictor
    _report(on_progress, 22, f"Modelo SAFIRE pronto ({device.type})")
    return predictor


def _run_safire_on_device(
    evidence_path: str,
    *,
    mode: Literal["binary", "multi"],
    cluster_type: str,
    kmeans_cluster_num: int,
    dbscan_eps: float,
    dbscan_min_samples: int,
    points_per_side: int,
    points_per_batch: int,
    on_progress: ProgressFn,
    device,
) -> SafireAnalysisResult:
    pps = _default_points_per_side(points_per_side, device)
    ppb = _default_points_per_batch(points_per_batch, device)

    _report(on_progress, 5, "Carregando evidencia")
    npimage, original, original_size = _load_rgb_arrays(evidence_path)
    input_preview = Image.fromarray(original, mode="RGB")

    predictor = _get_predictor(mode, pps, ppb, on_progress, device=device)
    _report(on_progress, 28, "Executando SAFIRE (prompts densos + clustering)")

    multi_segment: Image.Image | None = None
    cluster_count: int | None = None
    mean_score: float | None = None

    if mode == "binary":
        _anns, pred, _indices = predictor.safire_predict(npimage)
        heatmap = np.clip(pred.astype(np.float32), 0.0, 1.0)
        mean_score = float(np.mean(heatmap))
        # Partição multi-fonte auxiliar para visualização interativa (hover na UI).
        _report(on_progress, 72, "Gerando particao multi-fonte (preview)")
        _seed_safire_multi()
        multi_predictor = _get_predictor(
            "multi",
            pps,
            ppb,
            on_progress,
            device=device,
        )
        _anns_m, logits, _indices_m = multi_predictor.safire_predict(
            npimage,
            cluster_type=cluster_type,
            kmeans_num_clusters=kmeans_cluster_num,
            dbscan_eps=dbscan_eps,
            dbscan_min_samples=dbscan_min_samples,
        )
        cluster_count = int(logits.shape[0])
        multi_segment = _multi_logits_to_rgb(logits)
    else:
        _seed_safire_multi()
        _anns, logits, _indices = predictor.safire_predict(
            npimage,
            cluster_type=cluster_type,
            kmeans_num_clusters=kmeans_cluster_num,
            dbscan_eps=dbscan_eps,
            dbscan_min_samples=dbscan_min_samples,
        )
        cluster_count = int(logits.shape[0])
        multi_segment = _multi_logits_to_rgb(logits)
        heatmap = np.max(logits, axis=0)
        heatmap = np.clip(heatmap.astype(np.float32), 0.0, 1.0)
        mean_score = float(np.mean(heatmap))

    _report(on_progress, 88, "Ajustando mapas para dimensoes da imagem original")
    heatmap_inf = np.clip(heatmap, 0.0, 1.0)
    heatmap_full = (
        heatmap_inf
        if original_size == (1024, 1024)
        else _resize_map_to_original(heatmap_inf, original_size, nearest=True)
    )
    heatmap_img = _heatmap_to_pil(heatmap_full)
    overlay_img = _overlay_heatmap(original, heatmap_full)
    if multi_segment is not None:
        multi_segment = _resize_pil_to_original(multi_segment, original_size, nearest=True)
    _report(on_progress, 95, "SAFIRE concluido")

    return SafireAnalysisResult(
        mode=mode,
        input_image=input_preview,
        heatmap_image=heatmap_img,
        overlay_image=overlay_img,
        multi_segment_image=multi_segment,
        original_size=original_size,
        inference_size=(1024, 1024),
        cluster_type=cluster_type if mode == "multi" else None,
        cluster_count=cluster_count,
        mean_forgery_score=mean_score,
        inference_device=device.type,
        points_per_side_effective=pps,
        points_per_batch_effective=ppb,
    )


def run_safire_analysis(
    evidence_path: str,
    *,
    mode: str = "binary",
    cluster_type: str = "kmeans",
    kmeans_cluster_num: int = 3,
    dbscan_eps: float = 0.2,
    dbscan_min_samples: int = 1,
    points_per_side: int = 16,
    points_per_batch: int = 256,
    on_progress: ProgressFn = None,
) -> SafireAnalysisResult:
    """Run SAFIRE on one image path."""
    if mode not in ("binary", "multi"):
        raise ValueError("mode deve ser 'binary' ou 'multi'")

    _prepare_gpu_for_safire()

    def _run(device):
        return _run_safire_on_device(
            evidence_path,
            mode=mode,
            cluster_type=cluster_type,
            kmeans_cluster_num=kmeans_cluster_num,
            dbscan_eps=dbscan_eps,
            dbscan_min_samples=dbscan_min_samples,
            points_per_side=points_per_side,
            points_per_batch=points_per_batch,
            on_progress=on_progress,
            device=device,
        )

    gpu_fallback_reason: str | None = None
    gpu_fallback_warning: str | None = None

    def _on_gpu_oom(_detail: str) -> None:
        _report(
            on_progress,
            30,
            "VRAM insuficiente na GPU — continuando em CPU (lento, pode levar minutos)",
        )

    try:
        from core.gpu_inference import pop_gpu_fallback_reason, run_with_device_fallback

        result, _device = run_with_device_fallback(
            _run,
            on_fallback=clear_predictor_cache,
            on_before_cpu_fallback=_on_gpu_oom,
            allow_cpu_fallback=True,
        )
        gpu_fallback_reason = pop_gpu_fallback_reason()
        if result.inference_device == "cpu" and gpu_fallback_reason:
            gpu_fallback_warning = (
                "VRAM insuficiente na GPU (CUDA OOM). "
                "Continuando em CPU — resultado equivalente, porém muito mais lento."
            )
            result.gpu_fallback_reason = gpu_fallback_reason
            result.gpu_fallback_warning = gpu_fallback_warning
        return result
    finally:
        from core.gpu_residency import release_safire_cache_if_needed, touch_lru

        touch_lru("safire")
        release_safire_cache_if_needed()
