"""SLS (XLS-R + SLS classifier) spoofing inference in sliding windows."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import torch

from core.legacy.sls_spoofing.sls_runtime import (
    bootstrap_fairseq,
    resolve_sls_checkpoint_path,
    runtime_status,
)
from core.legacy.audio_spoofing.embedding_utils import aggregate_embeddings, register_sls_embedding_hook

SAMPLE_RATE = 16000
WINDOW_SECONDS = 4.0
PAD_SAMPLES = 64600
UNCERTAINTY_THRESHOLD = 0.65

_model: Any | None = None
_model_device: torch.device | None = None


def _softmax(logits: np.ndarray) -> np.ndarray:
    exp = np.exp(logits - np.max(logits))
    return exp / np.sum(exp)


def _pad_audio(audio: np.ndarray, max_len: int = PAD_SAMPLES) -> np.ndarray:
    x_len = audio.shape[0]
    if x_len >= max_len:
        return audio[:max_len]
    repeats = int(max_len / x_len) + 1
    return np.tile(audio, repeats)[:max_len]


def _split_audio(audio: np.ndarray, window_samples: int, stride_samples: int) -> list[tuple[int, np.ndarray]]:
    windows: list[tuple[int, np.ndarray]] = []
    total = len(audio)
    start = 0
    while start < total:
        end = min(start + window_samples, total)
        windows.append((start, audio[start:end]))
        if end == total:
            break
        start += stride_samples
    return windows


def _load_model(device: torch.device | str | None = None) -> tuple[Any, torch.device]:
    global _model, _model_device
    if device is None:
        device_obj = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    elif isinstance(device, str):
        device_obj = torch.device(device)
    else:
        device_obj = device

    if _model is not None and _model_device == device_obj:
        return _model, device_obj

    ok, reason = runtime_status()
    if not ok:
        raise RuntimeError(f"SLS indisponivel: {reason}")

    bootstrap_fairseq()
    vendor_root = Path(__file__).resolve().parents[5] / "Legados" / "audio" / "SLSforASVspoof-2021-DF"
    prev_cwd = os.getcwd()
    try:
        os.chdir(vendor_root)
        from model import Model  # type: ignore[import-not-found]

        model = Model(SimpleNamespace(), device_obj)
        ckpt_path = resolve_sls_checkpoint_path()
        if ckpt_path is None:
            raise RuntimeError("Checkpoint SLS ausente")
        raw = torch.load(ckpt_path, map_location=device_obj, weights_only=False)
        if any(str(k).startswith("module.") for k in raw):
            state = {k.replace("module.", "", 1): v for k, v in raw.items()}
        else:
            state = raw
        model.load_state_dict(state, strict=True)
        model.eval()
        model.to(device_obj)
    finally:
        os.chdir(prev_cwd)

    _model = model
    _model_device = device_obj
    return model, device_obj


def infer_sls_windows(
    audio: np.ndarray,
    sr: int,
    *,
    window_seconds: float = WINDOW_SECONDS,
    device: torch.device | str | int | None = None,
    return_embedding: bool = False,
) -> dict[str, Any]:
    """Run SLS classifier on ~4s windows (pad to 64600 samples @ 16 kHz)."""
    ok, reason = runtime_status()
    if not ok:
        raise RuntimeError(f"SLS indisponivel: {reason}")

    if sr != SAMPLE_RATE:
        import librosa

        audio = librosa.resample(audio.astype(np.float32), orig_sr=sr, target_sr=SAMPLE_RATE)

    device_obj: torch.device
    if isinstance(device, int):
        device_obj = torch.device(f"cuda:{device}" if device >= 0 else "cpu")
    elif isinstance(device, str):
        device_obj = torch.device(device)
    elif isinstance(device, torch.device):
        device_obj = device
    else:
        device_obj = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    model, device_obj = _load_model(device_obj)
    embed_hook = None
    embed_store: list[np.ndarray] = []
    if return_embedding:
        embed_hook, embed_store = register_sls_embedding_hook(model)
    window_samples = int(SAMPLE_RATE * window_seconds)
    windows = _split_audio(audio.astype(np.float32), window_samples, window_samples)

    window_results: list[dict[str, Any]] = []
    bonafide_log_scores: list[float] = []
    spoof_log_scores: list[float] = []
    window_embeddings: list[np.ndarray] = []

    try:
        for start, window in windows:
            embed_store.clear()
            padded = _pad_audio(window.astype(np.float32), PAD_SAMPLES)
            batch_x = torch.tensor(padded, dtype=torch.float32, device=device_obj).unsqueeze(0)
            with torch.no_grad():
                batch_out = model(batch_x)
                log_scores = batch_out.detach().cpu().numpy()[0]
            if return_embedding:
                if not embed_store:
                    raise RuntimeError("SLS embedding hook não capturou saída da penúltima camada")
                window_embeddings.append(embed_store[0].astype(np.float32))
            spoof_log = float(log_scores[0])
            bonafide_log = float(log_scores[1])
            probs = _softmax(np.array([spoof_log, bonafide_log]))

            window_results.append({
                "start_seconds": round(start / SAMPLE_RATE, 3),
                "center_seconds": round((start + len(window) / 2) / SAMPLE_RATE, 3),
                "duration_seconds": round(len(window) / SAMPLE_RATE, 3),
                "spoof_logit": round(spoof_log, 6),
                "bonafide_logit": round(bonafide_log, 6),
                "spoof_prob": round(float(probs[0]), 6),
                "bonafide_prob": round(float(probs[1]), 6),
                "bonafide_score": round(bonafide_log, 6),
            })
            spoof_log_scores.append(spoof_log)
            bonafide_log_scores.append(bonafide_log)
    finally:
        if embed_hook is not None:
            embed_hook.remove()

    if not window_results:
        raise RuntimeError("Nenhuma janela de audio gerada para SLS")

    agg_spoof = float(np.mean(spoof_log_scores))
    agg_bonafide = float(np.mean(bonafide_log_scores))
    agg_probs = _softmax(np.array([agg_spoof, agg_bonafide]))
    spoof_prob = float(agg_probs[0])
    bonafide_prob = float(agg_probs[1])

    if spoof_prob > UNCERTAINTY_THRESHOLD:
        label = "spoof"
    elif bonafide_prob > UNCERTAINTY_THRESHOLD:
        label = "bonafide"
    else:
        label = "uncertain"

    result: dict[str, Any] = {
        "windows": window_results,
        "aggregated": {
            "spoof_logit": round(agg_spoof, 6),
            "bonafide_logit": round(agg_bonafide, 6),
            "spoof_prob": round(spoof_prob, 6),
            "bonafide_prob": round(bonafide_prob, 6),
            "bonafide_score": round(agg_bonafide, 6),
            "label": label,
        },
        "window_count": len(window_results),
        "inference_device": str(device_obj),
    }
    if return_embedding:
        result["embedding"] = aggregate_embeddings(window_embeddings)
        result["embedding_dim"] = int(result["embedding"].shape[0])
    return result
