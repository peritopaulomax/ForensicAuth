"""Effort AIGI detection — single-image inference (fake probability p)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import cv2
import numpy as np
import torch
import torchvision.transforms as T
from PIL import Image

from core.gpu_inference import (
    device_display_label,
    release_gpu_memory,
    resolve_inference_device,
    run_with_device_fallback,
)
from core.legacy.effort.effort_model import EffortDetector
from core.legacy.effort.effort_runtime import (
    CLIP_HF_ID,
    effort_runtime_status,
    resolve_checkpoint,
    resolve_clip_path,
)

ProgressFn = Callable[[int, str], None] | None

CLIP_MEAN = (0.48145466, 0.4578275, 0.40821073)
CLIP_STD = (0.26862954, 0.26130258, 0.27577711)
INPUT_SIZE = 224


@dataclass
class EffortAnalysisResult:
    fake_probability: float
    predicted_label: int
    classification: str
    variant: str
    variant_label: str
    inference_device: str
    logits: list[float]
    gpu_fallback_reason: str | None = None
    gpu_fallback_warning: str | None = None


def _report(on_progress: ProgressFn, pct: int, label: str) -> None:
    if on_progress:
        on_progress(pct, label)


_model_cache: dict[str, EffortDetector] = {}


def _clip_source() -> str:
    local = resolve_clip_path()
    if local is not None:
        return str(local)
    return CLIP_HF_ID


def _load_model(variant: str, device: torch.device) -> EffortDetector:
    cache_key = f"{variant}:{device.type}"
    if cache_key in _model_cache:
        return _model_cache[cache_key]

    ckpt_path = resolve_checkpoint(variant)
    if ckpt_path is None:
        raise RuntimeError(f"Checkpoint Effort ausente para variante {variant}")

    model = EffortDetector(_clip_source())
    try:
        obj = torch.load(str(ckpt_path), map_location="cpu", weights_only=False)
    except TypeError:
        obj = torch.load(str(ckpt_path), map_location="cpu")

    state = obj.get("state_dict", obj) if isinstance(obj, dict) else obj
    if isinstance(state, dict):
        state = {k.replace("module.", ""): v for k, v in state.items()}
    model.load_state_dict(state, strict=False)
    model = model.to(device)
    model.eval()
    _model_cache[cache_key] = model
    return model


def _preprocess_pil(image: Image.Image) -> torch.Tensor:
    img_rgb = np.array(image.convert("RGB"))
    img_rgb = cv2.resize(img_rgb, (INPUT_SIZE, INPUT_SIZE), interpolation=cv2.INTER_LINEAR)
    transform = T.Compose(
        [
            T.ToTensor(),
            T.Normalize(CLIP_MEAN, CLIP_STD),
        ]
    )
    return transform(Image.fromarray(img_rgb)).unsqueeze(0)


def _preprocess_image(evidence_path: str) -> torch.Tensor:
    img_bgr = cv2.imread(evidence_path)
    if img_bgr is None:
        raise ValueError(f"Nao foi possivel ler a imagem: {evidence_path}")
    return _preprocess_pil(Image.fromarray(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)))


def clear_effort_model_cache() -> None:
    for model in list(_model_cache.values()):
        release_gpu_memory(model)
    _model_cache.clear()
    release_gpu_memory()


def effort_model_cache_keys() -> list[str]:
    return list(_model_cache.keys())


def _decision_label(score_ai: float) -> str:
    if score_ai > 0.66:
        return "AI"
    if score_ai < 0.34:
        return "REAL"
    return "Incerto"


def effort_row(
    model_label: str,
    fake_probability: float,
    *,
    inference_device: str = "cpu",
) -> list[str]:
    """Formato compativel com a tabela de detecção de imagens sintéticas (inclui coluna Dispositivo)."""
    import math

    ai_score = float(fake_probability)
    real_score = 1.0 - ai_score
    razao = real_score / ai_score if ai_score > 1e-9 else float("inf")
    log_razao = f"{math.log10(razao):.2f}" if math.isfinite(razao) else "inf"
    return [
        model_label,
        f"{ai_score:.4f}",
        f"{real_score:.4f}",
        log_razao,
        _decision_label(ai_score),
        device_display_label(inference_device),
    ]


def infer_effort_from_pil(image: Image.Image, *, variant: str, device: torch.device) -> EffortAnalysisResult:
    from core.legacy.effort.effort_runtime import EFFORT_VARIANTS

    model = _load_model(variant, device)
    tensor = _preprocess_pil(image).to(device)
    data = {"image": tensor, "label": torch.tensor([0], device=device)}

    with torch.no_grad():
        preds = model(data, inference=True)

    logits = preds["cls"].squeeze(0).detach().cpu().numpy()
    prob = float(preds["prob"].squeeze().detach().cpu().item())
    label = int(np.argmax(logits))
    classification = "SINTETICA" if label == 1 else "AUTENTICA"
    spec = EFFORT_VARIANTS[variant]
    return EffortAnalysisResult(
        fake_probability=prob,
        predicted_label=label,
        classification=classification,
        variant=variant,
        variant_label=spec["label"],
        inference_device=device.type,
        logits=[float(x) for x in logits.reshape(-1)],
    )


def predict_effort_rows(
    image: Image.Image,
    on_progress: ProgressFn = None,
) -> list[list[str]]:
    """Inferencia Effort (GenImage + Chameleon) para linhas extras na tabela de modelos."""
    from core.legacy.effort.effort_runtime import EFFORT_VARIANTS, effort_runtime_status

    rows: list[list[str]] = []
    ready_variants = [
        (variant_id, spec)
        for variant_id, spec in EFFORT_VARIANTS.items()
        if effort_runtime_status(variant=variant_id)[0]
    ]
    if not ready_variants:
        return rows

    preferred = resolve_inference_device()
    for idx, (variant_id, spec) in enumerate(ready_variants):
        pct = 52 + int(12 * (idx + 1) / len(ready_variants))
        dev_hint = device_display_label(preferred)
        _report(on_progress, pct, f"Inferindo Effort ({spec['label']}) em {dev_hint}…")

        def _run(dev: torch.device, *, _variant=variant_id):
            return infer_effort_from_pil(image, variant=_variant, device=dev)

        def _on_cpu_fallback(reason: str, *, _spec=spec) -> None:
            _report(
                on_progress,
                pct,
                f"Effort em CPU ({_spec['label']}) — fallback VRAM…",
            )

        result, device = run_with_device_fallback(
            _run,
            on_fallback=clear_effort_model_cache,
            on_before_cpu_fallback=_on_cpu_fallback,
        )
        preferred = device
        rows.append(
            effort_row(
                f"Effort ({spec['label']})",
                result.fake_probability,
                inference_device=device.type,
            )
        )
    return rows


def _infer(evidence_path: str, *, variant: str, device: torch.device) -> EffortAnalysisResult:
    from core.legacy.effort.effort_runtime import EFFORT_VARIANTS

    tensor_img = Image.open(evidence_path)
    return infer_effort_from_pil(tensor_img, variant=variant, device=device)


def run_effort_analysis(
    evidence_path: str,
    *,
    variant: str = "genimage",
    threshold: float = 0.5,
    on_progress: ProgressFn = None,
) -> EffortAnalysisResult:
    ok, reason = effort_runtime_status(variant=variant)
    if not ok:
        raise RuntimeError(reason)

    _report(on_progress, 10, "Preparando Effort")

    def _run(device: torch.device):
        _report(on_progress, 35, "Inferencia Effort")
        return _infer(evidence_path, variant=variant, device=device)

    result, device = run_with_device_fallback(
        _run,
        on_fallback=clear_effort_model_cache,
    )

    if result.fake_probability >= threshold:
        result = EffortAnalysisResult(
            fake_probability=result.fake_probability,
            predicted_label=1,
            classification="SINTETICA",
            variant=result.variant,
            variant_label=result.variant_label,
            inference_device=device.type,
            logits=result.logits,
            gpu_fallback_reason=result.gpu_fallback_reason,
            gpu_fallback_warning=result.gpu_fallback_warning,
        )
    else:
        result = EffortAnalysisResult(
            fake_probability=result.fake_probability,
            predicted_label=0,
            classification="AUTENTICA",
            variant=result.variant,
            variant_label=result.variant_label,
            inference_device=device.type,
            logits=result.logits,
            gpu_fallback_reason=result.gpu_fallback_reason,
            gpu_fallback_warning=result.gpu_fallback_warning,
        )

    _report(on_progress, 95, "Concluido")
    return result
