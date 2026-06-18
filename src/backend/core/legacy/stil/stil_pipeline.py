"""STIL — deteccao deepfake por inconsistencia espaco-temporal (ACM MM 2021)."""

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
import torchvision.transforms as T

from core.gpu_inference import device_display_label, release_gpu_memory, run_with_device_fallback
from core.legacy.stil.stil_model import STIL_Model
from core.legacy.stil.stil_runtime import CLIP_SIZE, MODEL_LABEL, THRESHOLD, stil_runtime_status, trained_weight_path

logger = logging.getLogger(__name__)
ProgressFn = Callable[[int, str], None] | None

_model_cache: dict[str, STIL_Model] = {}


@dataclass
class ClipResult:
    start_frame: int
    score: float
    decision: str


@dataclass
class StilAnalysis:
    video_decision: str
    mean_score: float
    max_score: float
    max_start_frame: int
    clip_results: list[ClipResult] = field(default_factory=list)
    scores_chart_path: str | None = None
    inference_device: str = "CPU"


def _report(fn: ProgressFn, pct: int, label: str) -> None:
    if fn:
        fn(pct, label)


def clear_stil_model_cache() -> None:
    _model_cache.clear()
    release_gpu_memory()


def _load_model(device: torch.device) -> STIL_Model:
    key = device.type
    if key in _model_cache:
        return _model_cache[key]
    model = STIL_Model(num_class=2, num_segment=CLIP_SIZE, add_softmax=False)
    ckpt = torch.load(trained_weight_path(), map_location=device, weights_only=False)
    if isinstance(ckpt, dict) and "state_dict" in ckpt:
        state = ckpt["state_dict"]
    elif isinstance(ckpt, dict) and "model" in ckpt:
        state = ckpt["model"]
    else:
        state = ckpt
    cleaned = {}
    for k, v in state.items():
        nk = k.replace("base_", "").replace("model.", "")
        if not nk.startswith("base_model."):
            nk = "base_model." + nk
        cleaned[nk] = v
    model.load_state_dict(cleaned, strict=False)
    model = model.to(device).eval()
    _model_cache[key] = model
    return model


def _sample_face_frames(video_path: str, sample_every: int, max_frames: int) -> list[tuple[int, np.ndarray]]:
    import decord

    decord.bridge.set_bridge("native")
    vr = decord.VideoReader(video_path, num_threads=4)
    frames: list[tuple[int, np.ndarray]] = []
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    for idx in range(0, len(vr), max(1, sample_every)):
        if len(frames) >= max_frames:
            break
        frame = vr[idx].asnumpy()
        gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
        faces = face_cascade.detectMultiScale(gray, 1.1, 4)
        if len(faces) == 0:
            crop = cv2.resize(frame, (224, 224))
        else:
            x, y, w, h = max(faces, key=lambda b: b[2] * b[3])
            crop = frame[y : y + h, x : x + w]
            crop = cv2.resize(crop, (224, 224))
        frames.append((idx, crop))
    return frames


def _build_clips(frames: list[tuple[int, np.ndarray]], clip_size: int) -> list[tuple[int, list[np.ndarray]]]:
    if len(frames) < clip_size:
        return []
    clips: list[tuple[int, list[np.ndarray]]] = []
    step = max(1, clip_size // 2)
    for i in range(0, len(frames) - clip_size + 1, step):
        chunk = frames[i : i + clip_size]
        clips.append((chunk[0][0], [f for _, f in chunk]))
    return clips


def _save_chart(clips: list[ClipResult], out_path: Path) -> str:
    if not clips:
        return ""
    xs = [c.start_frame for c in clips]
    ys = [c.score for c in clips]
    fig, ax = plt.subplots(figsize=(10, 3.2), dpi=120)
    colors = ["#dc2626" if s > THRESHOLD else "#16a34a" for s in ys]
    ax.bar(xs, ys, color=colors, width=max(1, min(xs) * 0.02 + 1))
    ax.axhline(THRESHOLD, color="#f59e0b", linestyle="--", linewidth=1.2)
    ax.set_xlabel("Frame inicial do clip")
    ax.set_ylabel("Score fake")
    ax.set_ylim(0, 1.05)
    ax.set_title(f"{MODEL_LABEL} — score por clip")
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, format="png")
    plt.close(fig)
    return str(out_path)


def run_stil_analysis(
    video_path: str,
    *,
    sample_every: int = 4,
    max_frames: int = 64,
    out_dir: Path | None = None,
    on_progress: ProgressFn = None,
) -> StilAnalysis:
    ok, reason = stil_runtime_status()
    if not ok:
        raise RuntimeError(reason)

    work = out_dir or Path(video_path).parent / "stil_tmp"
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)

    _report(on_progress, 10, "Amostrando frames e rostos")
    frames = _sample_face_frames(video_path, sample_every, max_frames)
    clips_data = _build_clips(frames, CLIP_SIZE)
    if not clips_data:
        raise ValueError(f"Video muito curto — necessario pelo menos {CLIP_SIZE} frames com rosto.")

    transform = T.Compose(
        [
            T.ToTensor(),
            T.Normalize(mean=[0.5, 0.5, 0.5], std=[0.5, 0.5, 0.5]),
        ]
    )

    def _infer(device: torch.device) -> StilAnalysis:
        model = _load_model(device)
        clip_results: list[ClipResult] = []
        total = len(clips_data)
        for i, (start_idx, imgs) in enumerate(clips_data):
            tensors = torch.stack([transform(img) for img in imgs]).unsqueeze(0)  # [1,T,C,H,W]
            bs, t, c, h, w = tensors.shape
            inp = tensors.view(bs, t * c, h, w).to(device)
            with torch.no_grad():
                logits = model(inp)
                prob = torch.softmax(logits, dim=1)[0, 1].item()
            decision = "Fake" if prob > THRESHOLD else "Real"
            clip_results.append(ClipResult(start_frame=start_idx, score=prob, decision=decision))
            _report(on_progress, 20 + int(70 * (i + 1) / total), f"STIL clip {i + 1}/{total}")

        scores = [c.score for c in clip_results]
        max_clip = max(clip_results, key=lambda c: c.score)
        chart = _save_chart(clip_results, work / "stil_scores_chart.png")
        return StilAnalysis(
            video_decision="Fake" if max_clip.score > THRESHOLD else "Real",
            mean_score=float(np.mean(scores)),
            max_score=max_clip.score,
            max_start_frame=max_clip.start_frame,
            clip_results=clip_results,
            scores_chart_path=chart or None,
            inference_device=device_display_label(device),
        )

    result, device = run_with_device_fallback(_infer)
    result.inference_device = device_display_label(device)
    _report(on_progress, 95, "Finalizando STIL")
    return result


def write_stil_report(analysis: StilAnalysis, out_dir: Path) -> tuple[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "technique": "stil_video_detection",
        "model_label": MODEL_LABEL,
        "threshold": THRESHOLD,
        "video_decision": analysis.video_decision,
        "mean_score": round(analysis.mean_score, 6),
        "max_score": round(analysis.max_score, 6),
        "max_start_frame": analysis.max_start_frame,
        "inference_device": analysis.inference_device,
        "clips": [
            {"start_frame": c.start_frame, "score": round(c.score, 6), "decision": c.decision}
            for c in analysis.clip_results
        ],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    json_path = out_dir / "stil_report.json"
    txt_path = out_dir / "stil_summary.txt"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    txt_path.write_text(
        "\n".join(
            [
                f"{MODEL_LABEL} — Relatorio",
                f"Decisao: {analysis.video_decision}",
                f"Score medio: {analysis.mean_score:.4f}",
                f"Score maximo: {analysis.max_score:.4f} (clip em frame {analysis.max_start_frame})",
                f"Clips analisados: {len(analysis.clip_results)}",
            ]
        ),
        encoding="utf-8",
    )
    return str(json_path), str(txt_path)
