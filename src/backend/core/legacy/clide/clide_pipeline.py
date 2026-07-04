"""CLIDE official single-image synthetic detection inference."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Callable, Literal

import torch
from PIL import Image

from core.gpu_inference import (
    device_display_label,
    release_gpu_memory,
    resolve_inference_device,
    run_with_device_fallback,
)
from core.legacy.clide.clide_runtime import (
    clide_clip_cache_dir,
    clide_runtime_status,
    resolve_rep_matrix,
    resolve_whitening_matrix,
)
logger = logging.getLogger(__name__)

ProgressFn = Callable[[int, str], None] | None
MODEL_LABEL = "CLIDE (local likelihood)"

_clip_cache: dict[str, tuple[torch.nn.Module, Callable]] = {}
_whitening_cache: dict[tuple[str, str], tuple[torch.Tensor, torch.Tensor]] = {}
_rep_cache: dict[tuple[str, str], torch.Tensor] = {}


@dataclass(frozen=True)
class ClideResult:
    likelihood: float
    ai_score: float
    squared_norm: float
    dimensions: int
    mode: str
    domain: str
    inference_device: str


def _report(on_progress: ProgressFn, pct: int, label: str) -> None:
    if on_progress:
        on_progress(pct, label)


def _load_clip(device: torch.device):
    cache_key = device.type
    if cache_key in _clip_cache:
        return _clip_cache[cache_key]

    import clip

    model, preprocess = clip.load(
        "ViT-L/14",
        device=device.type,
        download_root=str(clide_clip_cache_dir()),
    )
    model.eval()
    _clip_cache[cache_key] = (model, preprocess)
    return model, preprocess


def _load_whitening(domain: str, device: torch.device) -> tuple[torch.Tensor, torch.Tensor]:
    cache_key = (domain, device.type)
    if cache_key in _whitening_cache:
        return _whitening_cache[cache_key]

    path = resolve_whitening_matrix(domain)
    if path is None:
        raise RuntimeError(f"Matriz CLIDE ausente para dominio {domain}")
    w_mat, w_mean = torch.load(str(path), map_location=device, weights_only=False)
    w_mat = w_mat.to(device=device, dtype=torch.float32)
    w_mean = w_mean.to(device=device, dtype=torch.float32)
    _whitening_cache[cache_key] = (w_mat, w_mean)
    return w_mat, w_mean


def _load_rep_matrix(domain: str, device: torch.device) -> torch.Tensor:
    cache_key = (domain, device.type)
    if cache_key in _rep_cache:
        return _rep_cache[cache_key]
    path = resolve_rep_matrix(domain)
    if path is None:
        raise RuntimeError(f"Representative matrix CLIDE ausente para dominio {domain}")
    rep = torch.load(str(path), map_location=device, weights_only=False)
    rep = rep.to(device=device, dtype=torch.float32)
    _rep_cache[cache_key] = rep
    return rep


def clear_clide_model_cache() -> None:
    for model, _preprocess in list(_clip_cache.values()):
        release_gpu_memory(model)
    _clip_cache.clear()
    _whitening_cache.clear()
    _rep_cache.clear()
    release_gpu_memory()


def _embed_image(image: Image.Image, device: torch.device) -> torch.Tensor:
    model, preprocess = _load_clip(device)
    image_tensor = preprocess(image.convert("RGB")).unsqueeze(0).to(device)
    with torch.no_grad():
        return model.encode_image(image_tensor).squeeze(0).to(device=device, dtype=torch.float32)


def _score_from_squared_norm(squared_norm: float, dimensions: int) -> float:
    """Map CLIDE Mahalanobis distance to an anomaly/synthetic suspicion score."""
    try:
        from scipy.stats import chi2

        return float(chi2.cdf(max(0.0, squared_norm), max(1, dimensions)))
    except Exception:
        expected = max(1.0, float(dimensions))
        return float(1.0 / (1.0 + math.exp(-(squared_norm - expected) / math.sqrt(2.0 * expected))))


def infer_clide_from_pil(
    image: Image.Image,
    device: torch.device,
    *,
    mode: Literal["global", "local"] = "local",
    domain: Literal["general", "cars"] = "general",
    k: int = 500,
    m: int = 400,
) -> ClideResult:
    """Return the official CLIDE likelihood and a derived anomaly score.

    The official CLI uses local whitening by default; global whitening is only
    selected when `--use_global` is passed.
    """
    embedding = _embed_image(image, device)

    if mode == "local":
        rep_mat = _load_rep_matrix(domain, device)
        k_eff = min(int(k), int(rep_mat.shape[0]))
        similarities = torch.cosine_similarity(embedding, rep_mat, dim=1)
        top_k_indices = torch.topk(similarities, k=k_eff, largest=True).indices
        selected_rep = rep_mat[top_k_indices]
        from core.legacy.clide.clide_vendor import load_detection_module

        _, local_w = load_detection_module().sphx(selected_rep, m=m)
        w_mean = selected_rep.mean(dim=0)
        w_mat = local_w.to(device=device, dtype=torch.float32)
    else:
        w_mat, w_mean = _load_whitening(domain, device)

    dimensions = int(w_mat.shape[1])
    log_const = 0.5 * dimensions * torch.log(torch.tensor(2 * math.pi, device=device))
    whitened_embedding = (embedding - w_mean) @ w_mat
    squared_norm = float(whitened_embedding.norm().detach().cpu().item() ** 2)
    likelihood = float((-(log_const + 0.5 * whitened_embedding.norm() ** 2)).detach().cpu().item())
    ai_score = _score_from_squared_norm(squared_norm, dimensions)
    return ClideResult(
        likelihood=likelihood,
        ai_score=ai_score,
        squared_norm=squared_norm,
        dimensions=dimensions,
        mode=mode,
        domain=domain,
        inference_device=device.type,
    )


def predict_clide_row(image: Image.Image, on_progress: ProgressFn = None) -> list[str] | None:
    ok, reason = clide_runtime_status()
    if not ok:
        logger.debug("CLIDE indisponivel: %s", reason)
        return None

    preferred = resolve_inference_device()
    pct = 66
    _report(on_progress, pct, f"Inferindo {MODEL_LABEL} em {device_display_label(preferred)}...")

    def _run(dev: torch.device):
        return infer_clide_from_pil(image, dev)

    def _on_cpu_fallback(exc_reason: str) -> None:
        _report(on_progress, pct, f"{MODEL_LABEL} em CPU - fallback VRAM...")

    try:
        result, device = run_with_device_fallback(
            _run,
            on_fallback=clear_clide_model_cache,
            on_before_cpu_fallback=_on_cpu_fallback,
        )
    except Exception as exc:
        logger.warning("CLIDE falhou: %s", exc)
        return None

    return [
        MODEL_LABEL,
        f"{result.likelihood:.4f}",
        "N/A",
        f"||z||²={result.squared_norm:.2f}",
        "Sem limiar",
        device_display_label(device.type),
    ]
