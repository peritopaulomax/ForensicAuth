"""Official GRIP-UNINA TruFor test_docker inference (full resolution, map/conf/score)."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image

ProgressFn = Callable[[int, str], None] | None

VENDOR_SRC = Path(__file__).resolve().parents[5] / "vendor" / "grip-unina-trufor" / "src"
OFFICIAL_CKPT_NAME = "trufor.pth.tar"


@dataclass
class TruForOfficialResult:
    input_image: Image.Image
    heatmap_image: Image.Image
    score_map_image: Image.Image
    confidence_image: Image.Image
    overlay_image: Image.Image
    mask_image: Image.Image
    original_size: tuple[int, int]
    integrity_score: float
    mean_localization_score: float
    inference_device: str
    gpu_fallback_reason: str | None = None
    gpu_fallback_warning: str | None = None


TRUFOR_GPU_OOM_WARNING = (
    "VRAM insuficiente na GPU (CUDA OOM). "
    "Continuando em CPU — resultado equivalente, porém muito mais lento (pode levar vários minutos)."
)


def trufor_official_root() -> Path:
    return VENDOR_SRC


def resolve_official_checkpoint() -> Path | None:
    from core.legacy.imdlbenco.imdlbenco_runtime import imdlbenco_models_dir

    path = imdlbenco_models_dir() / "trufor" / OFFICIAL_CKPT_NAME
    if path.is_file() and path.stat().st_size > 1_000_000:
        return path
    return None


def official_runtime_ready() -> tuple[bool, str]:
    if not trufor_official_root().is_dir():
        return False, "Codigo TruFor oficial ausente em vendor/grip-unina-trufor/src."
    ckpt = resolve_official_checkpoint()
    if ckpt is None:
        return (
            False,
            f"Peso oficial ausente ({OFFICIAL_CKPT_NAME}). "
            "Execute: python scripts/download_trufor_official_weights.py",
        )
    try:
        import torch  # noqa: F401
        import yacs  # noqa: F401
    except ImportError as exc:
        return False, f"Dependencia TruFor ausente: {exc}"
    return True, ""


def _purge_conflicting_vendor_modules(vendor_root: str) -> None:
    for mod_name in ("config", "models", "data_core", "trufor_test"):
        mod = sys.modules.get(mod_name)
        mod_file = getattr(mod, "__file__", "") or ""
        if mod is not None and vendor_root not in mod_file:
            del sys.modules[mod_name]


@lru_cache(maxsize=1)
def _ensure_vendor_imports():
    import importlib

    vendor_root = str(trufor_official_root().resolve())
    _purge_conflicting_vendor_modules(vendor_root)
    if vendor_root not in sys.path:
        sys.path.insert(0, vendor_root)
    config_mod = importlib.import_module("config")
    builder_mod = importlib.import_module("models.cmx.builder_np_conf")
    return config_mod._C, builder_mod.myEncoderDecoder


def _load_config(ckpt_path: Path):
    config_cls, _ = _ensure_vendor_imports()
    yaml_path = trufor_official_root() / "trufor.yaml"
    config = config_cls.clone()
    config.defrost()
    config.merge_from_file(str(yaml_path))
    config.TEST.MODEL_FILE = str(ckpt_path)
    config.freeze()
    return config


def _load_image_tensor(evidence_path: str, device):
    import torch

    rgb = np.array(Image.open(evidence_path).convert("RGB"), dtype=np.float32)
    tensor = torch.tensor(rgb.transpose(2, 0, 1), dtype=torch.float32) / 256.0
    return tensor.unsqueeze(0).to(device), rgb.astype(np.uint8)


def _prepare_gpu_for_trufor() -> None:
    """Release VRAM from other ML plugins before TruFor full-res inference."""
    import logging

    import torch

    from core.gpu_inference import cuda_memory_snapshot, purge_foreign_gpu_model_caches

    before = cuda_memory_snapshot()
    purge_foreign_gpu_model_caches(include_trufor=True)
    after = cuda_memory_snapshot()
    logging.getLogger(__name__).info(
        "TruFor GPU prep: free %s MiB -> %s MiB (total %s MiB)",
        before.get("free_mb"),
        after.get("free_mb"),
        after.get("total_mb"),
    )


def _load_model(device):
    import torch

    ckpt_path = resolve_official_checkpoint()
    if ckpt_path is None:
        raise RuntimeError("Peso oficial TruFor ausente")

    cache_key = f"trufor_official:{device.type}"
    if not hasattr(_load_model, "_cache"):
        _load_model._cache = {}
    cached = _load_model._cache.get(cache_key)
    if cached is not None:
        return cached.to(device)

    _, confcmx = _ensure_vendor_imports()
    config = _load_config(ckpt_path)
    model = confcmx(cfg=config)
    checkpoint = torch.load(str(ckpt_path), map_location="cpu", weights_only=False)
    state = checkpoint["state_dict"] if isinstance(checkpoint, dict) and "state_dict" in checkpoint else checkpoint
    model.load_state_dict(state)
    model = model.to(device)
    model.eval()
    _load_model._cache[cache_key] = model
    return model


def _infer_official(evidence_path: str, device) -> dict[str, np.ndarray | float]:
    import torch
    import torch.nn.functional as F

    model = _load_model(device)
    rgb, original = _load_image_tensor(evidence_path, device)
    with torch.no_grad():
        pred, conf, det, _npp = model(rgb)
        loc = torch.squeeze(pred, 0)
        loc = F.softmax(loc, dim=0)[1].cpu().numpy()
        conf_map = None
        if conf is not None:
            conf_map = torch.sigmoid(torch.squeeze(conf, 0))[0].cpu().numpy()
        score = float(torch.sigmoid(det).item()) if det is not None else float(np.mean(loc))
    del pred, conf, det, _npp, rgb

    return {
        "map": loc.astype(np.float32),
        "conf": conf_map.astype(np.float32) if conf_map is not None else None,
        "score": score,
        "original_rgb": original,
    }


def _score_map_pil(loc_map: np.ndarray) -> Image.Image:
    arr = np.clip(loc_map, 0.0, 1.0)
    return Image.fromarray((arr * 255.0).astype(np.uint8), mode="L")


def _heatmap_pil(loc_map: np.ndarray) -> Image.Image:
    import matplotlib.cm as cm

    arr = np.clip(loc_map, 0.0, 1.0)
    rgb = (cm.RdBu_r(arr)[..., :3] * 255).astype(np.uint8)
    return Image.fromarray(rgb, mode="RGB")


def _confidence_pil(conf_map: np.ndarray | None, shape: tuple[int, int]) -> Image.Image:
    if conf_map is None:
        return Image.fromarray(np.zeros(shape, dtype=np.uint8), mode="L")
    arr = np.clip(conf_map, 0.0, 1.0)
    return Image.fromarray((arr * 255.0).astype(np.uint8), mode="L")


def _overlay(original: np.ndarray, heatmap_rgb: np.ndarray, alpha: float = 0.45) -> Image.Image:
    base = original.astype(np.float32)
    over = heatmap_rgb.astype(np.float32)
    blended = (base * (1.0 - alpha) + over * alpha).astype(np.uint8)
    return Image.fromarray(blended, mode="RGB")


def run_trufor_official_analysis(
    evidence_path: str,
    *,
    threshold: float = 0.5,
    on_progress: ProgressFn = None,
) -> TruForOfficialResult:
    from core.gpu_inference import (
        evict_cache_keys_on_device,
        pop_gpu_fallback_reason,
        run_with_device_fallback,
    )

    def _report(pct: int, label: str) -> None:
        if on_progress:
            on_progress(pct, label)

    ok, reason = official_runtime_ready()
    if not ok:
        raise RuntimeError(reason)

    _report(10, "Carregando TruFor oficial (GRIP-UNINA)")
    _prepare_gpu_for_trufor()

    def _run(device):
        device_label = "GPU (CUDA)" if device.type == "cuda" else "CPU (lento — pode levar minutos)"
        _report(35, f"Inferencia TruFor full-res · {device_label}")
        return _infer_official(evidence_path, device)

    used_cpu_fallback = False
    gpu_fallback_reason: str | None = None
    gpu_fallback_warning: str | None = None

    def _on_gpu_oom(_cuda_detail: str) -> None:
        _report(
            32,
            f"VRAM insuficiente na GPU — continuando em CPU (lento, pode levar minutos)",
        )

    try:
        payload, device = run_with_device_fallback(
            _run,
            on_fallback=lambda: evict_cache_keys_on_device(getattr(_load_model, "_cache", {})),
            on_before_cpu_fallback=_on_gpu_oom,
            allow_cpu_fallback=True,
        )
        used_cpu_fallback = device.type == "cpu"
        gpu_fallback_reason = pop_gpu_fallback_reason()
        if used_cpu_fallback and gpu_fallback_reason:
            gpu_fallback_warning = TRUFOR_GPU_OOM_WARNING
    finally:
        if used_cpu_fallback:
            evict_cache_keys_on_device(getattr(_load_model, "_cache", {}))

    loc = payload["map"]
    original = payload["original_rgb"]
    h, w = original.shape[:2]
    score_map_img = _score_map_pil(loc)
    heatmap_img = _heatmap_pil(loc)
    conf_img = _confidence_pil(payload.get("conf"), (h, w))
    heatmap_rgb = np.array(heatmap_img)
    overlay_img = _overlay(original, heatmap_rgb)
    mask = (loc >= threshold).astype(np.uint8) * 255

    _report(90, f"Gerando artefatos · {device.type.upper()}")
    return TruForOfficialResult(
        input_image=Image.fromarray(original, mode="RGB"),
        heatmap_image=heatmap_img,
        score_map_image=score_map_img,
        confidence_image=conf_img,
        overlay_image=overlay_img,
        mask_image=Image.fromarray(mask, mode="L"),
        original_size=(h, w),
        integrity_score=float(payload["score"]),
        mean_localization_score=float(np.mean(loc)),
        inference_device=device.type,
        gpu_fallback_reason=gpu_fallback_reason,
        gpu_fallback_warning=gpu_fallback_warning,
    )
