"""VideoFACT — deteccao de edicoes e deepfake em video (WACV 2024)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import cv2
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np
import torch
import torchvision
import yaml
from torch.utils.data import DataLoader

from core.gpu_inference import (
    device_display_label,
    release_gpu_memory,
    resolve_inference_device,
    run_with_device_fallback,
)
from core.legacy.videofact.videofact_runtime import (
    DF_THRESHOLD,
    MODEL_LABEL_DF,
    MODEL_LABEL_XFER,
    XFER_THRESHOLD,
    default_thresholds,
    videofact_config_path,
    videofact_runtime_status,
    videofact_vendor_dir,
    weight_path,
)
from core.legacy.videofact.videofact_vendor import videofact_vendor_context

logger = logging.getLogger(__name__)

ProgressFn = Callable[[int, str], None] | None

_model_cache: dict[str, Any] = {}


@dataclass
class FrameResult:
    frame_idx: int
    score: float
    decision: str
    heatmap_path: str | None = None


@dataclass
class ModeResult:
    mode: str
    model_label: str
    threshold: float
    video_decision: str
    mean_score: float
    max_score: float
    max_frame_idx: int
    frame_results: list[FrameResult] = field(default_factory=list)
    scores_chart_path: str | None = None
    inference_device: str = "CPU"


@dataclass
class VideoFactAnalysis:
    modes: list[ModeResult]
    total_frames_sampled: int
    sample_every: int
    inference_device: str


def _report(on_progress: ProgressFn, pct: int, label: str) -> None:
    if on_progress:
        on_progress(pct, label)


def clear_videofact_model_cache() -> None:
    for model in list(_model_cache.values()):
        release_gpu_memory(model)
    _model_cache.clear()
    release_gpu_memory()


def _load_config() -> dict[str, Any]:
    cfg_path = videofact_config_path()
    with open(cfg_path, encoding="utf-8") as fh:
        return yaml.full_load(fh)


def _get_model(mode: str, device: torch.device):
    cache_key = f"{mode}:{device.type}"
    if cache_key in _model_cache:
        return _model_cache[cache_key]

    with videofact_vendor_context():
        from model.common.videofact import VideoFACT as VideoFACT_Module
        from model.videofact_pl_wrapper import VideoFACTPLWrapper

        ckpt = str(weight_path(mode))
        config = _load_config()
        model = VideoFACTPLWrapper.load_from_checkpoint(
            ckpt,
            model=VideoFACT_Module,
            map_location=device,
            **config,
        )
        model = model.to(device).eval()

    _model_cache[cache_key] = model
    return model


def _build_dataloader(
    video_path: str,
    *,
    shuffle: bool,
    max_num_samples: int,
    sample_every: int,
    batch_size: int,
    num_workers: int,
):
    import decord
    import random

    decord.bridge.set_bridge("torch")
    vr = decord.VideoReader(video_path, num_threads=4)
    batch_idxs = list(range(0, len(vr), max(1, sample_every)))
    if shuffle:
        random.shuffle(batch_idxs)
    if max_num_samples > 0:
        batch_idxs = batch_idxs[:max_num_samples]
    batch_idxs = sorted(batch_idxs)
    if not batch_idxs:
        raise ValueError("Video sem frames legiveis para amostragem.")

    frame_batch = vr.get_batch(batch_idxs)
    frame_batch = frame_batch.permute(0, 3, 1, 2).float()
    if frame_batch.shape[2] > frame_batch.shape[3]:
        frame_batch = frame_batch.permute(0, 1, 3, 2)
    frame_batch = torchvision.transforms.functional.vflip(frame_batch)
    if frame_batch.shape[2] != 1080 or frame_batch.shape[3] != 1920:
        frame_batch = torchvision.transforms.functional.resize(
            frame_batch, (1080, 1920), antialias=True
        )

    return DataLoader(
        list(zip(frame_batch, batch_idxs)),
        batch_size=max(1, batch_size),
        num_workers=max(0, num_workers),
        pin_memory=torch.cuda.is_available(),
    ), len(batch_idxs)


@torch.no_grad()
def _process_frames(
    model,
    dataloader: DataLoader,
    *,
    threshold: float,
    forged_label: str,
    authentic_label: str,
    heatmap_dir: Path,
    on_progress: ProgressFn,
    progress_base: int,
    progress_span: int,
) -> list[FrameResult]:
    heatmap_dir.mkdir(parents=True, exist_ok=True)
    results: list[FrameResult] = []
    total_batches = max(1, len(dataloader))
    batch_no = 0

    for batch in dataloader:
        frames, idxs = batch
        class_out, patch_out = model(frames.to(model.device))
        class_out = torch.softmax(class_out.detach().cpu(), dim=1)
        patch_out = patch_out.detach().cpu()

        patch_preds = [
            model.patch_to_pixel_pred(
                pl,
                model.patch_size,
                model.img_size,
                min_thresh=0.1,
                max_num_regions=3,
                final_thresh=0.30,
            )
            for pl in patch_out
        ]
        pixel_preds = torch.vstack([pp.get_pixel_preds().unsqueeze(0) for pp in patch_preds])

        for idx, frame, pixel_pred, score_tensor in zip(
            idxs, frames, pixel_preds, class_out[:, 1]
        ):
            frame_idx = int(idx.item() if hasattr(idx, "item") else idx)
            score = float(score_tensor.item())
            decision = forged_label if score > threshold else authentic_label

            result_frame = frame.permute(1, 2, 0).cpu().numpy() / 255.0
            overlay = pixel_pred.unsqueeze(-1).repeat(1, 1, 3).numpy()
            result_frame = cv2.addWeighted(result_frame, 0.7, overlay, 0.3, 0)
            resize_to = (int(result_frame.shape[1] * 0.70), int(result_frame.shape[0] * 0.70))
            result_frame = cv2.resize(result_frame, resize_to)
            heatmap_path = heatmap_dir / f"frame_{frame_idx:06d}.jpg"
            cv2.imwrite(
                str(heatmap_path),
                cv2.cvtColor((result_frame * 255).astype(np.uint8), cv2.COLOR_RGB2BGR),
                [cv2.IMWRITE_JPEG_QUALITY, 75],
            )
            results.append(
                FrameResult(
                    frame_idx=frame_idx,
                    score=score,
                    decision=decision,
                    heatmap_path=str(heatmap_path),
                )
            )

        batch_no += 1
        pct = progress_base + int(progress_span * batch_no / total_batches)
        _report(on_progress, min(99, pct), f"VideoFACT — frames ({batch_no}/{total_batches})")

    results.sort(key=lambda r: r.frame_idx)
    return results


def _save_scores_chart(
    frame_results: list[FrameResult],
    *,
    title: str,
    threshold: float,
    out_path: Path,
) -> str:
    if not frame_results:
        return ""
    frames = [r.frame_idx for r in frame_results]
    scores = [r.score for r in frame_results]
    fig, ax = plt.subplots(figsize=(10, 3.5), dpi=120)
    colors = ["#dc2626" if s > threshold else "#16a34a" for s in scores]
    ax.bar(frames, scores, color=colors, width=max(1, min(frames) * 0.02 + 1))
    ax.axhline(threshold, color="#f59e0b", linestyle="--", linewidth=1.2, label=f"Limiar {threshold:.2f}")
    ax.set_xlabel("Frame")
    ax.set_ylabel("Score (forgery)")
    ax.set_ylim(0, 1.05)
    ax.set_title(title)
    ax.legend(loc="upper right", fontsize=8)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, format="png")
    plt.close(fig)
    return str(out_path)


def _run_mode(
    video_path: str,
    mode: str,
    *,
    out_dir: Path,
    shuffle: bool,
    max_num_samples: int,
    sample_every: int,
    batch_size: int,
    num_workers: int,
    on_progress: ProgressFn,
    progress_base: int,
    progress_span: int,
) -> ModeResult:
    thresholds = default_thresholds()
    if mode == "xfer":
        threshold = thresholds["xfer"]
        model_label = MODEL_LABEL_XFER
        forged_label = "Forged"
        authentic_label = "Authentic"
    else:
        threshold = thresholds["df"]
        model_label = MODEL_LABEL_DF
        forged_label = "Deepfaked"
        authentic_label = "Authentic"

    def _infer(device: torch.device) -> ModeResult:
        model = _get_model(mode, device)
        dataloader, _ = _build_dataloader(
            video_path,
            shuffle=shuffle,
            max_num_samples=max_num_samples,
            sample_every=sample_every,
            batch_size=batch_size,
            num_workers=num_workers,
        )
        heatmap_dir = out_dir / f"heatmaps_{mode}"
        frame_results = _process_frames(
            model,
            dataloader,
            threshold=threshold,
            forged_label=forged_label,
            authentic_label=authentic_label,
            heatmap_dir=heatmap_dir,
            on_progress=on_progress,
            progress_base=progress_base,
            progress_span=progress_span,
        )
        scores = [r.score for r in frame_results]
        max_idx = max(frame_results, key=lambda r: r.score).frame_idx if frame_results else 0
        max_score = max(scores) if scores else 0.0
        mean_score = float(np.mean(scores)) if scores else 0.0
        video_decision = forged_label if max_score > threshold else authentic_label
        chart_path = _save_scores_chart(
            frame_results,
            title=f"{model_label} — score por frame",
            threshold=threshold,
            out_path=out_dir / f"scores_chart_{mode}.png",
        )
        return ModeResult(
            mode=mode,
            model_label=model_label,
            threshold=threshold,
            video_decision=video_decision,
            mean_score=mean_score,
            max_score=max_score,
            max_frame_idx=max_idx,
            frame_results=frame_results,
            scores_chart_path=chart_path or None,
            inference_device=device_display_label(device),
        )

    result, device = run_with_device_fallback(_infer)
    result.inference_device = device_display_label(device)
    return result


def run_videofact_analysis(
    video_path: str,
    *,
    mode: str = "both",
    shuffle: bool = False,
    max_num_samples: int = 100,
    sample_every: int = 5,
    batch_size_xfer: int = 1,
    batch_size_df: int = 2,
    num_workers: int = 0,
    out_dir: Path | None = None,
    on_progress: ProgressFn = None,
) -> VideoFactAnalysis:
    ok, reason = videofact_runtime_status()
    if not ok:
        raise RuntimeError(reason)

    video_path = str(Path(video_path).resolve())
    if not Path(video_path).is_file():
        raise FileNotFoundError(f"Video nao encontrado: {video_path}")

    mode = mode.lower().strip()
    if mode not in ("xfer", "df", "both"):
        raise ValueError("mode deve ser 'xfer', 'df' ou 'both'")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    work_dir = out_dir or (videofact_vendor_dir() / "tmp" / f"videofact_{stamp}")
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    modes_to_run = ["xfer", "df"] if mode == "both" else [mode]
    ok_modes, reason_modes = videofact_runtime_status(require_modes=tuple(modes_to_run))
    if not ok_modes:
        raise RuntimeError(reason_modes)

    _report(on_progress, 5, "Preparando VideoFACT")
    device = resolve_inference_device()
    results: list[ModeResult] = []
    span = 80 // len(modes_to_run)

    for i, m in enumerate(modes_to_run):
        _report(on_progress, 10 + i * span, f"Carregando modelo VideoFACT ({m})")
        bs = batch_size_xfer if m == "xfer" else batch_size_df
        results.append(
            _run_mode(
                video_path,
                m,
                out_dir=work_dir,
                shuffle=shuffle,
                max_num_samples=max_num_samples,
                sample_every=sample_every,
                batch_size=bs,
                num_workers=num_workers,
                on_progress=on_progress,
                progress_base=10 + i * span,
                progress_span=span,
            )
        )

    _report(on_progress, 95, "Finalizando VideoFACT")
    total_sampled = len(results[0].frame_results) if results else 0
    return VideoFactAnalysis(
        modes=results,
        total_frames_sampled=total_sampled,
        sample_every=sample_every,
        inference_device=device_display_label(device),
    )


def analysis_to_report_dict(analysis: VideoFactAnalysis) -> dict[str, Any]:
    return {
        "technique": "videofact",
        "total_frames_sampled": analysis.total_frames_sampled,
        "sample_every": analysis.sample_every,
        "inference_device": analysis.inference_device,
        "modes": [
            {
                "mode": m.mode,
                "model_label": m.model_label,
                "threshold": m.threshold,
                "video_decision": m.video_decision,
                "mean_score": round(m.mean_score, 6),
                "max_score": round(m.max_score, 6),
                "max_frame_idx": m.max_frame_idx,
                "inference_device": m.inference_device,
                "frames": [
                    {
                        "frame_idx": fr.frame_idx,
                        "score": round(fr.score, 6),
                        "decision": fr.decision,
                        "heatmap": Path(fr.heatmap_path).name if fr.heatmap_path else None,
                    }
                    for fr in m.frame_results
                ],
            }
            for m in analysis.modes
        ],
        "thresholds": {"xfer": XFER_THRESHOLD, "df": DF_THRESHOLD},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def write_videofact_report(analysis: VideoFactAnalysis, out_dir: Path) -> tuple[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    report = analysis_to_report_dict(analysis)
    json_path = out_dir / "videofact_report.json"
    txt_path = out_dir / "videofact_summary.txt"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "VideoFACT — Relatorio de analise de video",
        f"Frames amostrados: {analysis.total_frames_sampled} (sample_every={analysis.sample_every})",
        f"Dispositivo: {analysis.inference_device}",
        "",
    ]
    for m in analysis.modes:
        lines.extend(
            [
                f"=== {m.model_label} ({m.mode}) ===",
                f"Decisao do video: {m.video_decision}",
                f"Score medio: {m.mean_score:.4f}",
                f"Score maximo: {m.max_score:.4f} (frame {m.max_frame_idx})",
                f"Limiar: {m.threshold:.2f}",
                "",
            ]
        )
    txt_path.write_text("\n".join(lines), encoding="utf-8")
    return str(json_path), str(txt_path)
