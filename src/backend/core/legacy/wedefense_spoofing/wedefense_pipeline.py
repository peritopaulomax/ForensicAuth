"""WeDefense ASV2025 WavLM Base + MHFA spoofing inference in sliding windows."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np
import torch
import yaml

from core.legacy.wedefense_spoofing.wedefense_runtime import (
    AVG_CHECKPOINT_NAME,
    LOCAL_CONFIG_NAME,
    bootstrap_wedefense,
    resolve_avg_checkpoint_path,
    resolve_model_dir,
    runtime_status,
)

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000
WINDOW_SECONDS = 4.0
UNCERTAINTY_THRESHOLD = 0.65

_model: Any | None = None
_model_device: torch.device | None = None
_dataset_args: dict[str, Any] | None = None


def _softmax(logits: np.ndarray) -> np.ndarray:
    exp = np.exp(logits - np.max(logits))
    return exp / np.sum(exp)


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


def _wedefense_probs_to_scores(logits: np.ndarray) -> tuple[float, float, float, float]:
    """Map WeDefense logits (idx0=bonafide, idx1=spoof) to VA Suite convention."""
    bonafide_log = float(logits[0])
    spoof_log = float(logits[1])
    probs = _softmax(np.array([bonafide_log, spoof_log]))
    bonafide_prob = float(probs[0])
    spoof_prob = float(probs[1])
    return spoof_log, bonafide_log, spoof_prob, bonafide_prob


def _load_backend_checkpoint(model: Any, path: str) -> None:
    """Load MHFA + projection from avg_model.pt (frontend vem do pytorch_model.bin)."""
    checkpoint = torch.load(path, map_location="cpu", weights_only=False)
    filtered = {k: v for k, v in checkpoint.items() if not k.startswith("frontend.")}
    missing, unexpected = model.load_state_dict(filtered, strict=False)
    for key in missing:
        if key.startswith("frontend."):
            continue
        logger.warning("WeDefense missing tensor: %s", key)
    for key in unexpected:
        logger.warning("WeDefense unexpected tensor: %s", key)


def _load_model(device: torch.device | str | None = None) -> tuple[Any, torch.device, dict[str, Any]]:
    global _model, _model_device, _dataset_args

    if device is None:
        device_obj = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    elif isinstance(device, str):
        device_obj = torch.device(device)
    else:
        device_obj = device

    if _model is not None and _model_device == device_obj and _dataset_args is not None:
        return _model, device_obj, _dataset_args

    ok, reason = runtime_status()
    if not ok:
        raise RuntimeError(f"WeDefense indisponivel: {reason}")

    bootstrap_wedefense()
    from wedefense.dataset.dataset_utils import apply_cmvn
    from wedefense.frontend.get_hf_ssl_pruning import HuggingfaceFrontend
    from wedefense.models.get_model import get_model
    from wedefense.models.projections import get_projection

    model_dir = resolve_model_dir()
    ckpt_path = resolve_avg_checkpoint_path()
    if model_dir is None or ckpt_path is None:
        raise RuntimeError("Checkpoint WeDefense ausente")

    config_path = model_dir / LOCAL_CONFIG_NAME
    if not config_path.is_file():
        from core.legacy.wedefense_spoofing.wedefense_runtime import ensure_local_config

        config_path = ensure_local_config()

    with open(config_path, encoding="utf-8") as fin:
        configs = yaml.safe_load(fin)

    ds_args = configs["dataset_args"]
    frontend_type = ds_args.get("frontend", "fbank")
    if frontend_type != "fbank" and not str(frontend_type).startswith("lfcc"):
        frontend_args_key = f"{frontend_type}_args"
        frontend = HuggingfaceFrontend(
            **ds_args[frontend_args_key],
            sample_rate=ds_args.get("resample_rate", SAMPLE_RATE),
        )
        configs["model_args"]["feat_dim"] = frontend.output_size()
        model = get_model(configs["model"])(**configs["model_args"])
        model.add_module("frontend", frontend)
    else:
        model = get_model(configs["model"])(**configs["model_args"])

    projection = get_projection(configs["projection_args"])
    model.add_module("projection", projection)
    _load_backend_checkpoint(model, str(ckpt_path))
    model.eval()
    model.to(device_obj)

    _model = model
    _model_device = device_obj
    _dataset_args = ds_args
    return model, device_obj, ds_args


def _infer_window(
    model: Any,
    ds_args: dict[str, Any],
    window: np.ndarray,
    device_obj: torch.device,
    *,
    return_embedding: bool = False,
) -> tuple[float, float, float, float] | tuple[tuple[float, float, float, float], np.ndarray]:
    from wedefense.dataset.dataset_utils import apply_cmvn

    wavs = torch.tensor(window.astype(np.float32), dtype=torch.float32, device=device_obj).unsqueeze(0)
    wavs_len = torch.LongTensor([wavs.shape[1]]).to(device_obj)
    cmvn_args = ds_args.get("cmvn_args", {})

    with torch.no_grad():
        features, _ = model.frontend(wavs, wavs_len)
        if ds_args.get("cmvn", True):
            features = apply_cmvn(features, **cmvn_args)
        outputs = model(features)
        embeds = outputs[-1] if isinstance(outputs, tuple) else outputs
        dummy_label = torch.zeros(embeds.shape[0], dtype=torch.long, device=device_obj)
        logits_out = model.projection(embeds, dummy_label)
        logits = logits_out[0] if isinstance(logits_out, tuple) else logits_out
        logits_np = logits.detach().cpu().numpy()[0]

    scores = _wedefense_probs_to_scores(logits_np)
    if return_embedding:
        return scores, embeds.detach().cpu().numpy()[0].astype(np.float32)
    return scores


def infer_wedefense_windows(
    audio: np.ndarray,
    sr: int,
    *,
    window_seconds: float = WINDOW_SECONDS,
    device: torch.device | str | int | None = None,
    return_embedding: bool = False,
) -> dict[str, Any]:
    """Run WeDefense on ~4s windows. Logits: idx0=bonafide, idx1=spoof."""
    ok, reason = runtime_status()
    if not ok:
        raise RuntimeError(f"WeDefense indisponivel: {reason}")

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

    model, device_obj, ds_args = _load_model(device_obj)
    window_samples = int(SAMPLE_RATE * window_seconds)
    windows = _split_audio(audio.astype(np.float32), window_samples, window_samples)

    window_results: list[dict[str, Any]] = []
    spoof_log_scores: list[float] = []
    bonafide_log_scores: list[float] = []
    window_embeddings: list[np.ndarray] = []

    for start, window in windows:
        infer_out = _infer_window(
            model, ds_args, window, device_obj, return_embedding=return_embedding
        )
        if return_embedding:
            (spoof_log, bonafide_log, spoof_prob, bonafide_prob), embedding = infer_out
            window_embeddings.append(embedding)
        else:
            spoof_log, bonafide_log, spoof_prob, bonafide_prob = infer_out
        window_results.append({
            "start_seconds": round(start / SAMPLE_RATE, 3),
            "center_seconds": round((start + len(window) / 2) / SAMPLE_RATE, 3),
            "duration_seconds": round(len(window) / SAMPLE_RATE, 3),
            "spoof_logit": round(spoof_log, 6),
            "bonafide_logit": round(bonafide_log, 6),
            "spoof_prob": round(spoof_prob, 6),
            "bonafide_prob": round(bonafide_prob, 6),
            "bonafide_score": round(bonafide_log, 6),
        })
        spoof_log_scores.append(spoof_log)
        bonafide_log_scores.append(bonafide_log)

    if not window_results:
        raise RuntimeError("Nenhuma janela de audio gerada para WeDefense")

    agg_spoof = float(np.mean(spoof_log_scores))
    agg_bonafide = float(np.mean(bonafide_log_scores))
    _, _, spoof_prob, bonafide_prob = _wedefense_probs_to_scores(
        np.array([agg_bonafide, agg_spoof])
    )

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
        "checkpoint": AVG_CHECKPOINT_NAME,
    }
    if return_embedding:
        from core.legacy.audio_spoofing.embedding_utils import aggregate_embeddings

        result["embedding"] = aggregate_embeddings(window_embeddings)
        result["embedding_dim"] = int(result["embedding"].shape[0])
    return result
