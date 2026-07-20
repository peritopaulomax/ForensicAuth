"""Official MIML APSC-Net integration.

The upstream project ships research scripts instead of a library API.  This
module keeps the vendor code isolated and exposes the same image/mask contract
used by the IMDL-BenCo adapter.
"""

from __future__ import annotations

import contextlib
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image

ProgressFn = Callable[[int, str], None] | None

_apsc_cache: dict[str, object] = {}


@dataclass
class MimlOfficialResult:
    input_image: Image.Image
    heatmap_image: Image.Image
    overlay_image: Image.Image
    mask_image: Image.Image
    original_size: tuple[int, int]
    mean_score: float
    inference_device: str
    gpu_fallback_reason: str | None = None
    gpu_fallback_warning: str | None = None


def _report(on_progress: ProgressFn, pct: int, label: str) -> None:
    if on_progress:
        on_progress(pct, label)


def _runtime():
    from core.legacy.imdlbenco import imdlbenco_runtime as runtime

    return runtime


def _snapshot_modules(prefixes: tuple[str, ...]) -> dict[str, object]:
    return {
        k: sys.modules[k]
        for k in list(sys.modules)
        if any(k == p or k.startswith(f"{p}.") for p in prefixes)
    }


def _purge_modules(prefixes: tuple[str, ...]) -> None:
    for key in [
        k
        for k in list(sys.modules)
        if any(k == p or k.startswith(f"{p}.") for p in prefixes)
    ]:
        del sys.modules[key]


@contextlib.contextmanager
def _vendor_context(vendor_dir: Path, prefixes: tuple[str, ...]):
    saved = _snapshot_modules(prefixes)
    _purge_modules(prefixes)
    root = str(vendor_dir)
    inserted = False
    if root not in sys.path:
        sys.path.insert(0, root)
        inserted = True
    try:
        yield
    finally:
        _purge_modules(prefixes)
        sys.modules.update(saved)
        if inserted:
            with contextlib.suppress(ValueError):
                sys.path.remove(root)


def _to_rgb(path: str | Path) -> Image.Image:
    return Image.open(path).convert("RGB")


def _heatmap_to_pil(score: np.ndarray) -> Image.Image:
    arr = np.clip(score * 255.0, 0, 255).astype(np.uint8)
    return Image.fromarray(arr, mode="L")


def _overlay(original: Image.Image, score: np.ndarray, alpha: float = 0.45) -> Image.Image:
    import matplotlib.cm as cm

    base = np.asarray(original.convert("RGB"), dtype=np.float32)
    colored = (cm.inferno(np.clip(score, 0.0, 1.0))[..., :3] * 255).astype(np.float32)
    blended = (base * (1.0 - alpha) + colored * alpha).astype(np.uint8)
    return Image.fromarray(blended, mode="RGB")


def _mask(score: np.ndarray, threshold: float) -> Image.Image:
    return Image.fromarray((score >= threshold).astype(np.uint8) * 255, mode="L")


def _normalize_prediction(pred: object, original_size: tuple[int, int]) -> np.ndarray:
    import cv2
    import torch

    if isinstance(pred, (list, tuple)) and pred:
        pred = pred[0]
    if isinstance(pred, torch.Tensor):
        pred = pred.detach().float().cpu().numpy()
    arr = np.asarray(pred)
    if arr.ndim == 3:
        if arr.shape[0] in (1, 2):
            arr = arr[-1]
        else:
            arr = arr[..., -1]
    arr = arr.astype(np.float32)
    if arr.max(initial=0.0) > 1.0:
        arr = arr / 255.0
    width, height = original_size
    if arr.shape[:2] != (height, width):
        arr = cv2.resize(arr, (width, height), interpolation=cv2.INTER_LINEAR)
    return np.clip(arr, 0.0, 1.0)


def official_runtime_ready(method: str) -> tuple[bool, str]:
    runtime = _runtime()
    if method == "miml_apscnet":
        vendor = runtime.miml_iml_vendor_root()
        if not vendor.is_dir():
            return False, "Repositorio MIML ausente em vendor/MIML."
        if runtime.resolve_miml_apsc_checkpoint() is None:
            return False, "Peso APSC-Net ausente: models/imdlbenco/miml/apsc/APSC-Net.pth."
        try:
            import torch  # noqa: F401
            with _vendor_context(vendor, ("mmcv", "mmseg", "mmcv_custom", "mmcv_custom_hornet")):
                from mmseg.apis import inference_segmentor, init_segmentor  # noqa: F401
        except ImportError:
            return False, "Dependencias APSC-Net ausentes: instale mmcv 1.3.x-1.7.x compativel com o ambiente CUDA."
        except AssertionError as exc:
            return False, f"Dependencia APSC-Net incompatível: {exc}"
        except Exception as exc:
            # Importlib can raise KeyError/ModuleNotFoundError when vendor context
            # purges a partially-loaded mmcv from sys.modules; treat as unavailable.
            return False, f"Dependencias APSC-Net indisponiveis: {type(exc).__name__}: {exc}"
        return True, ""

    return False, f"Metodo MIML desconhecido: {method}"


def run_miml_apscnet_analysis(
    evidence_path: str,
    *,
    threshold: float,
    on_progress: ProgressFn = None,
) -> MimlOfficialResult:
    import torch

    runtime = _runtime()
    vendor = runtime.miml_iml_vendor_root()
    ckpt = runtime.resolve_miml_apsc_checkpoint()
    if ckpt is None:
        raise RuntimeError("Peso APSC-Net ausente.")

    original = _to_rgb(evidence_path)
    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    cache_key = f"apsc:{device}:{ckpt}"

    with _vendor_context(vendor, ("mmcv", "mmseg", "mmcv_custom", "mmcv_custom_hornet")):
        from mmseg.apis import inference_segmentor, init_segmentor

        if cache_key not in _apsc_cache:
            _report(on_progress, 18, "Carregando APSC-Net")
            _apsc_cache[cache_key] = init_segmentor(
                str(vendor / "apscnet.py"),
                str(ckpt),
                device=device,
            )
        model = _apsc_cache[cache_key]
        _report(on_progress, 55, "Executando inferencia APSC-Net")
        pred = inference_segmentor(model, evidence_path)

    score = _normalize_prediction(pred, original.size)
    heatmap = _heatmap_to_pil(score)
    return MimlOfficialResult(
        input_image=original,
        heatmap_image=heatmap,
        overlay_image=_overlay(original, score),
        mask_image=_mask(score, threshold),
        original_size=original.size,
        mean_score=float(score.mean()),
        inference_device="GPU" if device.startswith("cuda") else "CPU",
    )

def clear_miml_model_cache() -> None:
    _apsc_cache.clear()
