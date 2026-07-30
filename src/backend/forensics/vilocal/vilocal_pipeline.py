"""ViLocal pipeline — video inpainting (contrastive) localization."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import cv2
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np
import torch
import torch.nn.functional as F

from core.gpu_inference import device_display_label, release_gpu_memory, run_with_device_fallback
from forensics.vilocal.vilocal_runtime import (
    DEFAULT_CLIP_LEN,
    DEFAULT_HEIGHT,
    DEFAULT_MAX_CLIPS,
    DEFAULT_SAMPLE_EVERY,
    DEFAULT_WIDTH,
    MODEL_LABEL,
    vilocal_runtime_status,
    weight_path,
)
from forensics.vilocal.vilocal_vendor import vilocal_vendor_context

logger = logging.getLogger(__name__)
ProgressFn = Callable[[int, str], None] | None

_model_cache: dict[str, torch.nn.Module] = {}


@dataclass
class ClipResult:
    start_frame: int
    mean_mask_ratio: float
    max_mask_ratio: float


@dataclass
class ViLocalAnalysis:
    mean_mask_ratio: float
    max_mask_ratio: float
    max_start_frame: int
    threshold: float
    clip_results: list[ClipResult] = field(default_factory=list)
    scores_chart_path: str | None = None
    overlay_preview_path: str | None = None
    mask_preview_path: str | None = None
    heatmap_preview_path: str | None = None
    input_preview_path: str | None = None
    inference_device: str = "CPU"
    clip_len: int = DEFAULT_CLIP_LEN
    input_height: int = DEFAULT_HEIGHT
    input_width: int = DEFAULT_WIDTH


def _report(fn: ProgressFn, pct: int, label: str) -> None:
    if fn:
        fn(pct, label)


def clear_vilocal_model_cache() -> None:
    _model_cache.clear()
    release_gpu_memory()


def _patch_srm_device(SRM_cls) -> None:
    """SRM3D oficial força CUDA; alinhar peso ao device do input."""

    def forward(self, input):  # noqa: ANN001
        weight = self.weight.to(device=input.device, dtype=input.dtype)
        result = F.conv3d(input, weight=weight, stride=(1, 1, 1), padding=(1, 2, 2))
        return torch.clamp(result, min=0.0, max=4.0)

    SRM_cls.forward = forward  # type: ignore[method-assign]


def _load_model(device: torch.device) -> torch.nn.Module:
    key = device.type
    if key in _model_cache:
        return _model_cache[key]
    with vilocal_vendor_context():
        import SRM_3D as srm_mod
        from model import ViLocal

        _patch_srm_device(srm_mod.SRM3DMoudle)
        model = ViLocal()
        raw = torch.load(weight_path(), map_location="cpu", weights_only=False)
        if isinstance(raw, dict) and "state_dict" in raw:
            raw = raw["state_dict"]
        elif isinstance(raw, dict) and "model" in raw:
            raw = raw["model"]
        state = dict(raw)
        if any(k.startswith("module.") for k in state):
            state = {k.replace("module.", "", 1): v for k, v in state.items()}
        info = model.load_state_dict(state, strict=False)
        if info.missing_keys or info.unexpected_keys:
            logger.warning(
                "ViLocal load_state_dict missing=%s unexpected=%s",
                len(info.missing_keys),
                len(info.unexpected_keys),
            )
        model = model.to(device).eval()
    _model_cache[key] = model
    return model


def _sample_clips(
    video_path: str,
    sample_every: int,
    max_clips: int,
    clip_len: int,
) -> tuple[list[tuple[int, list[np.ndarray]]], tuple[int, int]]:
    """Return list of (start_frame_idx, RGB frames[clip_len]) and original (H,W)."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Nao foi possivel abrir o video: {video_path}")
    frames: list[tuple[int, np.ndarray]] = []
    origin_shape = (0, 0)
    try:
        idx = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            if idx % max(1, sample_every) == 0:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                if not frames:
                    origin_shape = rgb.shape[:2]
                frames.append((idx, rgb))
            idx += 1
    finally:
        cap.release()
    if not frames:
        raise ValueError("Nenhum frame lido do video")

    if len(frames) < clip_len:
        last_idx, last_frame = frames[-1]
        while len(frames) < clip_len:
            frames.append((last_idx, last_frame.copy()))

    clips: list[tuple[int, list[np.ndarray]]] = []
    step = max(1, clip_len)
    for i in range(0, max(1, len(frames) - clip_len + 1), step):
        start = frames[i][0]
        clip_frames = [frames[min(i + k, len(frames) - 1)][1] for k in range(clip_len)]
        clips.append((start, clip_frames))
        if len(clips) >= max_clips:
            break
    return clips, origin_shape


def _frames_to_tensor(
    frames: list[np.ndarray],
    height: int,
    width: int,
) -> torch.Tensor:
    """Official preprocess: Resize(H,W) + ToTensor → (1, 3, T, H, W)."""
    from PIL import Image
    from torchvision.transforms import transforms

    resize = transforms.Resize((height, width), interpolation=Image.BILINEAR)
    to_tensor = transforms.ToTensor()
    tensors = []
    for fr in frames:
        img = Image.fromarray(fr)
        tensors.append(to_tensor(resize(img)))
    return torch.stack(tensors, dim=1).unsqueeze(0)  # 1,C,T,H,W


def _mask_ratio(mask: np.ndarray) -> float:
    if mask.size == 0:
        return 0.0
    return float((mask > 0).mean())


def _overlay(image: np.ndarray, mask: np.ndarray, alpha: float = 0.45) -> np.ndarray:
    red = np.zeros_like(image)
    red[:, :, 0] = 255
    m = np.stack([mask, mask, mask], axis=2) / 255.0
    out = image.astype(np.float32) * (1 - m * alpha) + red.astype(np.float32) * m * alpha
    return np.clip(out, 0, 255).astype(np.uint8)


def _probs_to_logits(probs: np.ndarray, eps: float = 1e-4) -> np.ndarray:
    p = np.clip(probs.astype(np.float64), eps, 1.0 - eps)
    return np.log(p / (1.0 - p)).astype(np.float32)


def _logits_heatmap_rgb(logits: np.ndarray) -> np.ndarray:
    flat = logits[np.isfinite(logits)]
    if flat.size == 0:
        return np.zeros((*logits.shape, 3), dtype=np.uint8)
    lo, hi = np.percentile(flat, [2, 98])
    if hi <= lo:
        lo, hi = float(flat.min()), float(flat.max())
    if hi <= lo:
        norm = np.zeros_like(logits, dtype=np.float32)
    else:
        norm = np.clip((logits - lo) / (hi - lo), 0.0, 1.0).astype(np.float32)
    cmap = plt.get_cmap("turbo")
    rgba = cmap(norm)
    return (rgba[:, :, :3] * 255).astype(np.uint8)


def _overlay_heatmap(image: np.ndarray, heatmap_rgb: np.ndarray, alpha: float = 0.5) -> np.ndarray:
    h = min(image.shape[0], heatmap_rgb.shape[0])
    w = min(image.shape[1], heatmap_rgb.shape[1])
    out = image.copy().astype(np.float32)
    heat = heatmap_rgb[:h, :w].astype(np.float32)
    out[:h, :w] = out[:h, :w] * (1.0 - alpha) + heat * alpha
    return np.clip(out, 0, 255).astype(np.uint8)


def _upsample_map(arr: np.ndarray, out_hw: tuple[int, int]) -> np.ndarray:
    H, W = out_hw
    return cv2.resize(arr, (W, H), interpolation=cv2.INTER_LINEAR)


def _infer_clip(
    model: torch.nn.Module,
    device: torch.device,
    frames: list[np.ndarray],
    height: int,
    width: int,
    threshold: float,
) -> tuple[float, np.ndarray, np.ndarray]:
    """Return (mask_ratio, soft_full_res, mask_full_res) for middle/representative frame size."""
    tensor = _frames_to_tensor(frames, height, width).to(device)
    with torch.no_grad():
        logits = model(tensor)
        soft = torch.sigmoid(logits).detach().float().cpu().numpy()
    if soft.ndim == 4:
        soft = soft[0, 0]
    elif soft.ndim == 3:
        soft = soft[0]
    origin_hw = frames[0].shape[:2]
    soft_full = _upsample_map(soft.astype(np.float32), origin_hw)
    soft_full = np.clip(soft_full, 0.0, 1.0)
    mask_full = (soft_full > threshold).astype(np.uint8) * 255
    return _mask_ratio(mask_full), soft_full, mask_full


def _write_chart(clip_results: list[ClipResult], out_path: Path) -> None:
    xs = [c.start_frame for c in clip_results]
    ys = [c.mean_mask_ratio for c in clip_results]
    fig, ax = plt.subplots(figsize=(8, 3))
    ax.plot(xs, ys, marker="o", linewidth=1.5)
    ax.set_xlabel("Frame inicial do clip")
    ax.set_ylabel("Razao media da mascara")
    ax.set_title("ViLocal — localizacao por clip")
    ax.set_ylim(0, 1)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def run_vilocal_analysis(
    evidence_path: str,
    *,
    sample_every: int = DEFAULT_SAMPLE_EVERY,
    max_clips: int = DEFAULT_MAX_CLIPS,
    clip_len: int = DEFAULT_CLIP_LEN,
    input_height: int = DEFAULT_HEIGHT,
    input_width: int = DEFAULT_WIDTH,
    mask_threshold: float = 0.5,
    out_dir: str | Path,
    on_progress: ProgressFn = None,
) -> ViLocalAnalysis:
    ok, reason = vilocal_runtime_status()
    if not ok:
        raise RuntimeError(reason)
    if clip_len != DEFAULT_CLIP_LEN:
        raise ValueError(f"ViLocal requer clip_len={DEFAULT_CLIP_LEN} (mapa do frame central)")

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    _report(on_progress, 5, "Amostrando clips")
    clips, _origin = _sample_clips(evidence_path, sample_every, max_clips, clip_len)

    def _run(device: torch.device):
        _report(on_progress, 20, f"Carregando modelo em {device.type}")
        model = _load_model(device)
        outs: list[tuple[float, np.ndarray, np.ndarray, list[np.ndarray]]] = []
        for ci, (_sf, frames) in enumerate(clips):
            pct = 40 + int(50 * ci / max(1, len(clips)))
            _report(on_progress, pct, f"Inferencia clip {ci + 1}/{len(clips)}")
            ratio, soft, mask = _infer_clip(
                model, device, frames, input_height, input_width, mask_threshold
            )
            outs.append((ratio, soft, mask, frames))
        return outs

    infer_out, used_device = run_with_device_fallback(_run)
    device_label = device_display_label(used_device)

    clip_results: list[ClipResult] = []
    best_soft: np.ndarray | None = None
    best_mask: np.ndarray | None = None
    best_frame: np.ndarray | None = None
    best_ratio = -1.0

    for (start_frame, _), (ratio, soft, mask, frames) in zip(clips, infer_out):
        clip_results.append(
            ClipResult(
                start_frame=int(start_frame),
                mean_mask_ratio=float(ratio),
                max_mask_ratio=float(ratio),
            )
        )
        if ratio > best_ratio:
            best_ratio = ratio
            best_soft = soft
            best_mask = mask
            best_frame = frames[clip_len // 2]

    mean_all = float(np.mean([c.mean_mask_ratio for c in clip_results])) if clip_results else 0.0
    max_clip = max(clip_results, key=lambda c: c.mean_mask_ratio) if clip_results else None

    chart_path = None
    if len(clip_results) > 1:
        chart_path = out_dir / "vilocal_scores_chart.png"
        _write_chart(clip_results, chart_path)

    overlay_path = mask_path = heatmap_path = input_path = None
    from PIL import Image

    if best_frame is not None and best_mask is not None and best_soft is not None:
        input_path = out_dir / "vilocal_input_preview.png"
        Image.fromarray(best_frame).save(input_path)
        overlay_path = out_dir / "vilocal_overlay_preview.png"
        Image.fromarray(_overlay(best_frame, best_mask)).save(overlay_path)
        mask_path = out_dir / "vilocal_mask_preview.png"
        Image.fromarray(best_mask).save(mask_path)
        heat = _logits_heatmap_rgb(_probs_to_logits(best_soft))
        heatmap_path = out_dir / "vilocal_heatmap_preview.png"
        Image.fromarray(_overlay_heatmap(best_frame, heat)).save(heatmap_path)

    _report(on_progress, 90, "Gerando relatorio")
    return ViLocalAnalysis(
        mean_mask_ratio=mean_all,
        max_mask_ratio=float(max_clip.mean_mask_ratio) if max_clip else 0.0,
        max_start_frame=int(max_clip.start_frame) if max_clip else 0,
        threshold=mask_threshold,
        clip_results=clip_results,
        scores_chart_path=str(chart_path) if chart_path else None,
        overlay_preview_path=str(overlay_path) if overlay_path else None,
        mask_preview_path=str(mask_path) if mask_path else None,
        heatmap_preview_path=str(heatmap_path) if heatmap_path else None,
        input_preview_path=str(input_path) if input_path else None,
        inference_device=device_label,
        clip_len=clip_len,
        input_height=input_height,
        input_width=input_width,
    )


def write_vilocal_report(analysis: ViLocalAnalysis, out_dir: str | Path) -> tuple[str, str]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "model": MODEL_LABEL,
        "technique": "vilocal",
        "weights_profile": "train_VI_OP",
        "mean_mask_ratio": analysis.mean_mask_ratio,
        "max_mask_ratio": analysis.max_mask_ratio,
        "max_start_frame": analysis.max_start_frame,
        "threshold": analysis.threshold,
        "clip_len": analysis.clip_len,
        "input_size": [analysis.input_height, analysis.input_width],
        "inference_device": analysis.inference_device,
        "clips": [
            {
                "start_frame": c.start_frame,
                "mean_mask_ratio": c.mean_mask_ratio,
                "max_mask_ratio": c.max_mask_ratio,
            }
            for c in analysis.clip_results
        ],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "note": "Sem rotulo autentico/manipulado — interpretar mascara/heatmap.",
    }
    json_path = out_dir / "vilocal_report.json"
    txt_path = out_dir / "vilocal_summary.txt"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    txt_path.write_text(
        (
            f"ViLocal ({MODEL_LABEL})\n"
            f"Razao media mascara: {analysis.mean_mask_ratio:.4f}\n"
            f"Razao max (clip): {analysis.max_mask_ratio:.4f} @ frame {analysis.max_start_frame}\n"
            f"Threshold mascara binaria: {analysis.threshold}\n"
            f"Input: {analysis.input_height}x{analysis.input_width}, clip_len={analysis.clip_len}\n"
            f"Dispositivo: {analysis.inference_device}\n"
            f"Nota: sem rotulo autentico/manipulado — interpretar mascara/heatmap.\n"
        ),
        encoding="utf-8",
    )
    return str(json_path), str(txt_path)
