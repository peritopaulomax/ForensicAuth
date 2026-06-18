"""Low-Resolution Fake Video Detection — baseline temporal (TUM)."""

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
from core.legacy.lowres_fake_video.lfv_runtime import MODEL_LABEL, THRESHOLD, lfv_runtime_status, weight_path
from core.legacy.lowres_fake_video.lfv_vendor import lfv_vendor_context

logger = logging.getLogger(__name__)
ProgressFn = Callable[[int, str], None] | None

_model_cache: dict[str, object] = {}


@dataclass
class FrameScore:
    frame_idx: int
    score: float
    decision: str


@dataclass
class LfvAnalysis:
    video_decision: str
    mean_score: float
    max_score: float
    max_frame_idx: int
    frame_scores: list[FrameScore] = field(default_factory=list)
    scores_chart_path: str | None = None
    inference_device: str = "CPU"


def _report(fn: ProgressFn, pct: int, label: str) -> None:
    if fn:
        fn(pct, label)


def clear_lfv_model_cache() -> None:
    _model_cache.clear()
    release_gpu_memory()


def _map_checkpoint_to_baseline(state: dict) -> tuple[dict, int]:
    """Mapeia checkpoint TUM ou DeepfakeBench para BaselineModel (model.*).

    Retorna (state_dict, input_size). DeepfakeBench usa backbone.* e treino em 256px;
    TUM original usa model.* ou chaves nuas e 299px.
    """
    raw = state.get("state_dict", state) if isinstance(state, dict) else state
    if not isinstance(raw, dict):
        raise ValueError("Checkpoint LFV invalido: esperado dict ou state_dict.")

    uses_deepfakebench = any(k.replace("module.", "").startswith("backbone.") for k in raw)
    input_size = 256 if uses_deepfakebench else 299

    cleaned: dict[str, object] = {}
    for key, value in raw.items():
        nk = key.replace("module.", "")
        if nk.startswith("backbone."):
            nk = "model." + nk[len("backbone.") :]
        elif nk.startswith("model."):
            pass
        else:
            nk = "model." + nk
        cleaned[nk] = value
    return cleaned, input_size


def _load_model(device: torch.device):
    wp = weight_path()
    mtime = wp.stat().st_mtime if wp.is_file() else 0.0
    key = f"{device.type}:{wp}:{mtime}"
    if key in _model_cache:
        return _model_cache[key]

    with lfv_vendor_context():
        import torch.nn as nn
        from networks import xception as xception_mod
        from networks.baseline import BaselineModel

        # Evita download ImageNet (URL lip6.fr com certificado expirado); pesos vêm do checkpoint.
        backbone = xception_mod.xception(pretrained=False)
        num_ftrs = backbone.last_linear.in_features
        backbone.last_linear = nn.Linear(num_ftrs, 2)
        model = BaselineModel.__new__(BaselineModel)
        nn.Module.__init__(model)
        model.model_choice = "xception"
        model.model = backbone

    state = torch.load(wp, map_location=device, weights_only=False)
    cleaned, input_size = _map_checkpoint_to_baseline(state)
    missing = model.load_state_dict(cleaned, strict=False)
    if missing.missing_keys:
        loaded = len(cleaned) - len(missing.unexpected_keys)
        logger.warning(
            "LFV: checkpoint incompleto (%d chaves inesperadas, %d ausentes). "
            "Ausentes: %s",
            len(missing.unexpected_keys),
            len(missing.missing_keys),
            missing.missing_keys[:8],
        )
        if len(missing.missing_keys) > 20:
            raise RuntimeError(
                "Pesos LFV incompativeis com o modelo (mapeamento falhou). "
                f"Chaves ausentes: {len(missing.missing_keys)}"
            )
    model = model.to(device).eval()
    model._lfv_input_size = input_size  # type: ignore[attr-defined]
    _model_cache[key] = model
    return model


def _iter_face_frames(
    video_path: str, sample_every: int, max_frames: int, *, input_size: int = 299
) -> list[tuple[int, np.ndarray]]:
    import decord

    decord.bridge.set_bridge("native")
    vr = decord.VideoReader(video_path, num_threads=4)
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    out: list[tuple[int, np.ndarray]] = []
    for idx in range(0, len(vr), max(1, sample_every)):
        if len(out) >= max_frames:
            break
        frame = vr[idx].asnumpy()
        gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
        faces = cascade.detectMultiScale(gray, 1.1, 4)
        if len(faces) == 0:
            crop = cv2.resize(frame, (input_size, input_size), interpolation=cv2.INTER_CUBIC)
        else:
            x, y, w, h = max(faces, key=lambda b: b[2] * b[3])
            crop = cv2.resize(
                frame[y : y + h, x : x + w],
                (input_size, input_size),
                interpolation=cv2.INTER_CUBIC,
            )
        out.append((idx, crop))
    return out


def _chart(frames: list[FrameScore], path: Path) -> str:
    if not frames:
        return ""
    fig, ax = plt.subplots(figsize=(10, 3.2), dpi=120)
    xs = [f.frame_idx for f in frames]
    ys = [f.score for f in frames]
    colors = ["#dc2626" if s > THRESHOLD else "#16a34a" for s in ys]
    ax.bar(xs, ys, color=colors)
    ax.axhline(THRESHOLD, color="#f59e0b", linestyle="--")
    ax.set_ylim(0, 1.05)
    ax.set_title(f"{MODEL_LABEL} — score por frame")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, format="png")
    plt.close(fig)
    return str(path)


def run_lfv_analysis(
    video_path: str,
    *,
    sample_every: int = 5,
    max_frames: int = 80,
    out_dir: Path | None = None,
    on_progress: ProgressFn = None,
) -> LfvAnalysis:
    ok, reason = lfv_runtime_status()
    if not ok:
        raise RuntimeError(reason)

    work = Path(out_dir or Path(video_path).parent / "lfv_tmp")
    work.mkdir(parents=True, exist_ok=True)
    _report(on_progress, 10, "Amostrando frames")

    transform = T.Compose([T.ToTensor(), T.Normalize([0.5] * 3, [0.5] * 3)])

    def _infer(device: torch.device) -> LfvAnalysis:
        model = _load_model(device)
        input_size = int(getattr(model, "_lfv_input_size", 299))
        frames = _iter_face_frames(video_path, sample_every, max_frames, input_size=input_size)
        if not frames:
            raise ValueError("Nenhum frame legivel no video.")

        scores: list[FrameScore] = []
        total = len(frames)
        for i, (idx, img) in enumerate(frames):
            tensor = transform(img).unsqueeze(0).to(device)
            with torch.no_grad():
                logits = model(tensor)
                prob = torch.softmax(logits, dim=1)[0, 1].item()
            scores.append(
                FrameScore(
                    frame_idx=idx,
                    score=prob,
                    decision="Fake" if prob > THRESHOLD else "Real",
                )
            )
            _report(on_progress, 15 + int(75 * (i + 1) / total), f"LFV frame {i + 1}/{total}")
        vals = [s.score for s in scores]
        max_fr = max(scores, key=lambda s: s.score)
        chart = _chart(scores, work / "lfv_scores_chart.png")
        return LfvAnalysis(
            video_decision="Fake" if max_fr.score > THRESHOLD else "Real",
            mean_score=float(np.mean(vals)),
            max_score=max_fr.score,
            max_frame_idx=max_fr.frame_idx,
            frame_scores=scores,
            scores_chart_path=chart or None,
            inference_device=device_display_label(device),
        )

    result, device = run_with_device_fallback(_infer)
    result.inference_device = device_display_label(device)
    return result


def write_lfv_report(analysis: LfvAnalysis, out_dir: Path) -> tuple[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "technique": "lowres_fake_video",
        "model_label": MODEL_LABEL,
        "threshold": THRESHOLD,
        "video_decision": analysis.video_decision,
        "mean_score": round(analysis.mean_score, 6),
        "max_score": round(analysis.max_score, 6),
        "max_frame_idx": analysis.max_frame_idx,
        "inference_device": analysis.inference_device,
        "frames": [
            {"frame_idx": f.frame_idx, "score": round(f.score, 6), "decision": f.decision}
            for f in analysis.frame_scores
        ],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    jp = out_dir / "lfv_report.json"
    tp = out_dir / "lfv_summary.txt"
    jp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tp.write_text(
        f"{MODEL_LABEL}\nDecisao: {analysis.video_decision}\n"
        f"Score max: {analysis.max_score:.4f} (frame {analysis.max_frame_idx})\n",
        encoding="utf-8",
    )
    return str(jp), str(tp)
