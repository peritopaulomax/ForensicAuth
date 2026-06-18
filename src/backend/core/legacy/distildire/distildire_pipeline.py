"""DistilDIRE inference — deteccao de imagens sintetizadas por difusao (ICML 2024)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import numpy as np
from PIL import Image

from core.gpu_inference import (
    device_display_label,
    evict_cache_keys_on_device,
    pop_gpu_fallback_reason,
    release_gpu_memory,
    run_with_device_fallback,
)
from core.legacy.distildire.distildire_runtime import (
    MODEL_LABEL,
    TECHNIQUE_NAME,
    CheckpointKind,
    adm_model_path,
    checkpoint_path,
    distildire_runtime_status,
)
from core.legacy.distildire.distildire_vendor import distildire_vendor_context

ProgressFn = Callable[[int, str], None] | None

_DEFAULT_THRESHOLD = 0.5

_model_cache: dict[str, Any] = {}


@dataclass
class DistilDireAnalysis:
    df_probability: float
    prediction: str
    threshold: float
    checkpoint: str
    input_image: Image.Image
    eps_heatmap: Image.Image | None
    inference_device: str
    gpu_fallback_reason: str | None = None


def _report(on_progress: ProgressFn, pct: int, label: str) -> None:
    if on_progress:
        on_progress(pct, label)


def _classify(probability: float, threshold: float) -> str:
    return "FAKE" if probability >= threshold else "REAL"


def clear_distildire_model_cache() -> None:
    evict_cache_keys_on_device(_model_cache)
    _model_cache.clear()
    release_gpu_memory()


def _eps_to_heatmap(eps_tensor) -> Image.Image:
    import torch

    arr = eps_tensor.detach().float().cpu()
    if arr.ndim == 4:
        arr = arr[0]
    mag = arr.abs().mean(dim=0).numpy()
    mag = (mag - mag.min()) / (mag.max() - mag.min() + 1e-8)
    mag_u8 = (mag * 255).astype(np.uint8)
    try:
        import cv2

        colored = cv2.applyColorMap(mag_u8, cv2.COLORMAP_INFERNO)
        rgb = cv2.cvtColor(colored, cv2.COLOR_BGR2RGB)
        return Image.fromarray(rgb)
    except Exception:
        return Image.fromarray(mag_u8, mode="L")


def _load_stack(device, checkpoint_kind: CheckpointKind):
    import torch
    import torchvision.transforms.functional as TF
    from torchvision import transforms

    cache_key = f"{device}:{checkpoint_kind}"
    if cache_key in _model_cache:
        return _model_cache[cache_key]

    with distildire_vendor_context():
        from guided_diffusion.compute_dire_eps import (
            create_dicts_for_static_init,
            dire_get_first_step_noise,
        )
        from guided_diffusion.guided_diffusion.script_util import (
            create_model_and_diffusion,
            dict_parse,
            model_and_diffusion_defaults,
        )
        from networks.distill_model import DistilDIRE

        ckpt = checkpoint_path(checkpoint_kind)
        adm_path = adm_model_path()

        args = create_dicts_for_static_init()
        args["timestep_respacing"] = "ddim20"
        args["model_path"] = str(adm_path)

        adm_model, diffusion = create_model_and_diffusion(
            **dict_parse(args, model_and_diffusion_defaults().keys())
        )
        adm_model.load_state_dict(torch.load(adm_path, map_location="cpu", weights_only=False))
        adm_model.to(device)
        adm_model.eval()

        student = DistilDIRE(device)
        state_dict = torch.load(ckpt, map_location="cpu", weights_only=False)["model"]
        state_dict = {k.replace("module.", ""): v for k, v in state_dict.items()}
        student.load_state_dict(state_dict)
        student.to(device)
        student.eval()

        trans = transforms.Compose(
            (
                transforms.Resize(256, antialias=True),
                transforms.CenterCrop((256, 256)),
            )
        )

        stack = {
            "student": student,
            "adm_model": adm_model,
            "diffusion": diffusion,
            "args": args,
            "trans": trans,
            "to_tensor": TF.to_tensor,
            "dire_get_first_step_noise": dire_get_first_step_noise,
        }
        _model_cache[cache_key] = stack
        return stack


def _infer_on_device(
    evidence_path: str,
    *,
    checkpoint_kind: CheckpointKind,
    threshold: float,
    generate_visuals: bool,
    device,
) -> DistilDireAnalysis:
    import torch

    stack = _load_stack(device, checkpoint_kind)
    img = Image.open(evidence_path).convert("RGB")
    preview = img.copy()
    preview.thumbnail((512, 512), Image.Resampling.LANCZOS)

    tensor = stack["to_tensor"](img) * 2 - 1
    tensor = stack["trans"](tensor).to(device).unsqueeze(0)

    with torch.no_grad():
        eps = stack["dire_get_first_step_noise"](
            tensor, stack["adm_model"], stack["diffusion"], stack["args"], device
        )
        logit = stack["student"](tensor, eps)["logit"].sigmoid()
        probability = float(logit.median().item())

    eps_heatmap = _eps_to_heatmap(eps) if generate_visuals else None

    return DistilDireAnalysis(
        df_probability=probability,
        prediction=_classify(probability, threshold),
        threshold=threshold,
        checkpoint=checkpoint_kind,
        input_image=preview,
        eps_heatmap=eps_heatmap,
        inference_device=device_display_label(device),
    )


def run_distildire_analysis(
    evidence_path: str,
    *,
    checkpoint: CheckpointKind = "imagenet",
    threshold: float = _DEFAULT_THRESHOLD,
    generate_visuals: bool = True,
    on_progress: ProgressFn = None,
) -> DistilDireAnalysis:
    ok, reason = distildire_runtime_status(require_checkpoint=checkpoint)
    if not ok:
        raise RuntimeError(reason)

    _report(on_progress, 5, "Preparando DistilDIRE e modelo ADM")
    _report(on_progress, 15, "DDIM inversion (primeiro passo de ruido)")

    def _run(device):
        _report(on_progress, 35, f"Inferencia DistilDIRE ({device_display_label(device)})")
        result = _infer_on_device(
            evidence_path,
            checkpoint_kind=checkpoint,
            threshold=threshold,
            generate_visuals=generate_visuals,
            device=device,
        )
        _report(on_progress, 85, "Finalizando resultado")
        return result

    analysis, _device = run_with_device_fallback(_run)
    analysis.gpu_fallback_reason = pop_gpu_fallback_reason()
    _report(on_progress, 100, "Concluido")
    return analysis


def analysis_to_report_dict(analysis: DistilDireAnalysis) -> dict[str, Any]:
    return {
        "technique": TECHNIQUE_NAME,
        "model_label": MODEL_LABEL,
        "checkpoint": analysis.checkpoint,
        "df_probability": round(analysis.df_probability, 6),
        "prediction": analysis.prediction,
        "threshold": analysis.threshold,
        "inference_device": analysis.inference_device,
        "gpu_fallback_reason": analysis.gpu_fallback_reason,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def write_distildire_report(analysis: DistilDireAnalysis, out_dir: Path) -> tuple[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    report = analysis_to_report_dict(analysis)
    json_path = out_dir / "distildire_report.json"
    txt_path = out_dir / "distildire_summary.txt"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    txt_path.write_text(
        "\n".join(
            [
                "DistilDIRE — Relatorio de deteccao de imagem sintetica",
                f"Checkpoint: {analysis.checkpoint}",
                f"Probabilidade deepfake/sintetica: {analysis.df_probability:.4f}",
                f"Limiar: {analysis.threshold:.2f}",
                f"Classificacao: {analysis.prediction}",
                f"Dispositivo: {analysis.inference_device}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return str(json_path), str(txt_path)
