"""IAPL (CVPR 2026) — test-time adaptive synthetic image detection."""

from __future__ import annotations

import logging
import os
from argparse import Namespace
from contextlib import nullcontext
from copy import deepcopy
from dataclasses import dataclass
from typing import Callable

import torch
import torch.nn.functional as F
from PIL import Image
from torchvision import transforms

from core.gpu_inference import (
    device_display_label,
    is_cuda_oom_or_device_error,
    release_gpu_memory,
    resolve_inference_device,
)
from core.gpu_residency import prepare_vram_for_iapl_if_needed
from core.legacy.effort.effort_pipeline import effort_row
from core.legacy.iapl.iapl_runtime import (
    IAPL_VARIANTS,
    iapl_runtime_status,
    resolve_checkpoint,
    resolve_clip_pt,
)
from core.legacy.iapl.iapl_vendor import iapl_vendor_context

logger = logging.getLogger(__name__)

ProgressFn = Callable[[int, str], None] | None

IMG_RESOLUTION = 256
CROP_RESOLUTION = 224
EVAL_BATCH_SIZE = 32
SELECTION_P = 0.2


@dataclass
class _LoadedIapl:
    model: torch.nn.Module
    augmenter: object
    pretrained_ctx: torch.Tensor
    optimizer: torch.optim.Optimizer
    optim_state: dict
    args: Namespace


_model_cache: dict[str, _LoadedIapl] = {}


def _report(on_progress: ProgressFn, pct: int, label: str) -> None:
    if on_progress:
        on_progress(pct, label)


def _build_args(variant: str) -> Namespace:
    spec = IAPL_VARIANTS[variant]
    return Namespace(
        backbone="CLIP:ViT-L/14",
        n_ctx=2,
        prompt_depth=9,
        vision_width=1024,
        image_size=CROP_RESOLUTION,
        vit_adapter_list=[3, 7, 11, 15, 19, 23],
        text_adapter_list=[],
        gate=True,
        condition=True,
        smooth=True,
        tta=True,
        use_contrast=False,
        loss_adapter=1.0,
        loss_contrast=1.0,
        loss_condition=1.0,
        selection_p=SELECTION_P,
        ois=True,
        tta_steps=spec["tta_steps"],
        lr=spec["lr"],
        dataset=spec["dataset"],
    )


def _binary_entropy(logits: torch.Tensor, selection_p: float, ois: bool) -> tuple[torch.Tensor, torch.Tensor]:
    select_num = int(len(logits) * selection_p)

    if ois:
        with torch.no_grad():
            confidence = F.softmax(torch.abs(torch.sigmoid(logits) - 0.5) * 2, dim=0)
            _, index = torch.topk(confidence, select_num, dim=0)
        probs = torch.sigmoid(logits)
        avg_probs = probs[index].mean()
        loss = -(avg_probs * torch.log(avg_probs + 1e-8) + (1 - avg_probs) * torch.log(1 - avg_probs + 1e-8))
        return loss, index

    with torch.no_grad():
        confidence = F.softmax(torch.abs(torch.sigmoid(logits) - 0.5) * 2, dim=0)
        _, index = torch.topk(confidence, max(select_num - 1, 1), dim=0)
        index = torch.cat([torch.tensor([0], device=index.device).long(), index], dim=0)
    probs = torch.sigmoid(logits)
    avg_probs = probs[index].mean()
    loss = -(avg_probs * torch.log(avg_probs + 1e-8) + (1 - avg_probs) * torch.log(1 - avg_probs + 1e-8))
    return loss, index


def _test_time_tuning(
    model: torch.nn.Module,
    inputs: torch.Tensor,
    optimizer: torch.optim.Optimizer,
    args: Namespace,
) -> torch.Tensor:
    no_sync = getattr(model, "no_sync", nullcontext)

    for _ in range(args.tta_steps):
        with no_sync():
            output, _, _ = model(inputs)
            loss, index = _binary_entropy(output.squeeze(), args.selection_p, args.ois)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
    return index


def _load_variant(variant: str, device: torch.device) -> _LoadedIapl:
    cache_key = f"{variant}:{device.type}"
    if cache_key in _model_cache:
        return _model_cache[cache_key]

    clip_path = resolve_clip_pt()
    ckpt_path = resolve_checkpoint(variant)
    if clip_path is None or ckpt_path is None:
        raise RuntimeError(f"Pesos IAPL ausentes para variante {variant}")

    args = _build_args(variant)

    with iapl_vendor_context(clip_path=clip_path):
        import importlib

        from augmix import AugMixAugmenter  # type: ignore[import-untyped]

        build_model = importlib.import_module("models").build_model

        base_transform = transforms.Compose(
            [
                transforms.Resize((IMG_RESOLUTION, IMG_RESOLUTION)),
                transforms.CenterCrop(CROP_RESOLUTION),
            ]
        )
        preprocess = transforms.Compose(
            [
                transforms.ToTensor(),
                transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
            ]
        )
        augmenter = AugMixAugmenter(
            base_transform,
            IMG_RESOLUTION,
            CROP_RESOLUTION,
            preprocess,
            n_views=EVAL_BATCH_SIZE - 1,
            augmix=False,
            dataset=args.dataset,
        )

        model = build_model(args)
        try:
            checkpoint = torch.load(str(ckpt_path), map_location="cpu", weights_only=False)
        except TypeError:
            checkpoint = torch.load(str(ckpt_path), map_location="cpu")

        model.load_state_dict(checkpoint["model"])
        pretrained_ctx = checkpoint["model"]["prompt_learner.ctx"].clone()
        model.to(device)
        model.freeze_tta()

        optimizer = torch.optim.AdamW(
            [{"params": [p for _, p in model.named_parameters() if p.requires_grad]}],
            args.lr,
        )
        optim_state = deepcopy(optimizer.state_dict())

    loaded = _LoadedIapl(
        model=model,
        augmenter=augmenter,
        pretrained_ctx=pretrained_ctx,
        optimizer=optimizer,
        optim_state=optim_state,
        args=args,
    )
    _model_cache[cache_key] = loaded
    return loaded


def clear_iapl_model_cache() -> None:
    for entry in list(_model_cache.values()):
        release_gpu_memory(entry.model)
    _model_cache.clear()
    release_gpu_memory()


def iapl_model_cache_keys() -> list[str]:
    return list(_model_cache.keys())


def _iapl_allow_cpu_fallback() -> bool:
    return os.environ.get("IAPL_ALLOW_CPU_FALLBACK", "").lower() in {"1", "true", "yes"}


def infer_iapl_from_pil(
    image: Image.Image,
    *,
    variant: str,
    device: torch.device,
    on_progress: ProgressFn = None,
    progress_pct: int = 69,
) -> float:
    """Probabilidade de imagem sintetica (fake) via IAPL + TTA."""
    label = IAPL_VARIANTS.get(variant, {}).get("label", variant)
    dev_label = device_display_label(device)
    _report(on_progress, progress_pct, f"Carregando IAPL ({label}) em {dev_label}…")

    bundle = _load_variant(variant, device)
    model = bundle.model
    args = bundle.args

    tensor_views = bundle.augmenter(image.convert("RGB"))
    images = torch.stack(tensor_views, dim=0).to(device)

    with torch.no_grad():
        model.prompt_learner.ctx.copy_(bundle.pretrained_ctx)
    bundle.optimizer.load_state_dict(bundle.optim_state)

    _report(on_progress, progress_pct, f"TTA IAPL ({label}, 32 views) em {dev_label}…")

    use_amp = device.type == "cuda"
    amp_ctx = torch.amp.autocast(device_type=device.type, dtype=torch.bfloat16) if use_amp else nullcontext()

    with amp_ctx:
        model.train()
        select_index = _test_time_tuning(model, images, bundle.optimizer, args)

    with amp_ctx:
        with torch.no_grad():
            model.eval()
            if args.ois:
                outputs = model(images[select_index])
                preds = outputs.sigmoid()
                conf_idx = torch.max(torch.abs(preds - 0.5), dim=0)[1]
                pred = preds[conf_idx]
            else:
                pred = model(images[0:1]).sigmoid().squeeze()

    return float(pred.detach().cpu().item())


def _run_iapl_on_device(
    image: Image.Image,
    *,
    variant_id: str,
    device: torch.device,
    on_progress: ProgressFn,
    progress_pct: int,
) -> float:
    return infer_iapl_from_pil(
        image,
        variant=variant_id,
        device=device,
        on_progress=on_progress,
        progress_pct=progress_pct,
    )


def _infer_iapl_with_gpu_retry(
    image: Image.Image,
    *,
    variant_id: str,
    on_progress: ProgressFn,
    progress_pct: int,
    vram_prepared: bool,
) -> tuple[float, torch.device]:
    import torch

    if not vram_prepared:
        prepare_vram_for_iapl_if_needed()

    device = resolve_inference_device()
    if device.type != "cuda":
        return _run_iapl_on_device(
            image,
            variant_id=variant_id,
            device=device,
            on_progress=on_progress,
            progress_pct=progress_pct,
        ), device

    last_exc: RuntimeError | None = None
    for attempt in range(2):
        try:
            return _run_iapl_on_device(
                image,
                variant_id=variant_id,
                device=device,
                on_progress=on_progress,
                progress_pct=progress_pct,
            ), device
        except RuntimeError as exc:
            if not is_cuda_oom_or_device_error(exc):
                raise
            last_exc = exc
            logger.warning(
                "IAPL OOM na GPU (tentativa %s/2): %s",
                attempt + 1,
                exc,
            )
            clear_iapl_model_cache()
            prepare_vram_for_iapl_if_needed()

    assert last_exc is not None
    if not _iapl_allow_cpu_fallback():
        raise RuntimeError(
            "VRAM insuficiente para IAPL na GPU (TTA ViT-L/14). "
            "Reinicie o backend ou defina IAPL_ALLOW_CPU_FALLBACK=1 para tentar CPU (lento). "
            f"Detalhe: {last_exc}"
        ) from last_exc

    spec = IAPL_VARIANTS[variant_id]
    label = f"IAPL ({spec['label']})"
    _report(on_progress, progress_pct, f"{label} em CPU — fallback VRAM…")
    cpu = torch.device("cpu")
    return _run_iapl_on_device(
        image,
        variant_id=variant_id,
        device=cpu,
        on_progress=on_progress,
        progress_pct=progress_pct,
    ), cpu


def predict_iapl_rows(
    image: Image.Image,
    on_progress: ProgressFn = None,
    *,
    vram_prepared: bool = False,
) -> list[list[str]]:
    """Linhas IAPL para a tabela de detecção de imagens sinteticas."""
    rows: list[list[str]] = []
    ready_variants = [
        (variant_id, spec)
        for variant_id, spec in IAPL_VARIANTS.items()
        if iapl_runtime_status(variant=variant_id)[0]
    ]
    if not ready_variants:
        return rows

    if not vram_prepared:
        _report(on_progress, 64, "Liberando VRAM para IAPL (Effort/SAFE/CNN)…")
        prepare_vram_for_iapl_if_needed()

    for idx, (variant_id, spec) in enumerate(ready_variants):
        pct = 65 + int(4 * (idx + 1) / len(ready_variants))
        label = f"IAPL ({spec['label']})"

        try:
            prob, device = _infer_iapl_with_gpu_retry(
                image,
                variant_id=variant_id,
                on_progress=on_progress,
                progress_pct=pct,
                vram_prepared=True,
            )
            rows.append(effort_row(label, prob, inference_device=device.type))
        except Exception as exc:
            logger.warning("IAPL falhou para %s: %s", variant_id, exc)
            _report(on_progress, pct, f"IAPL indisponivel: {exc}")

    return rows


def warm_iapl_models(*, device: torch.device | None = None) -> list[str]:
    target = device or resolve_inference_device()
    loaded: list[str] = []
    dummy = Image.new("RGB", (CROP_RESOLUTION, CROP_RESOLUTION), color=(100, 120, 140))
    for variant_id in IAPL_VARIANTS:
        ok, _ = iapl_runtime_status(variant=variant_id)
        if not ok:
            continue
        try:
            infer_iapl_from_pil(dummy, variant=variant_id, device=target)
            loaded.append(variant_id)
        except Exception as exc:
            logger.warning("IAPL warmup falhou para %s: %s", variant_id, exc)
    return loaded
