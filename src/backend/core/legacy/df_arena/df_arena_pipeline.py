"""Wrapper local para o detector DF Arena 1B de spoofing de áudio.

O código original do modelo está em Legados/audio/DF_ARENA_1B. Este módulo
adiciona Legados/audio/DF_ARENA_1B ao sys.path em tempo de execução, sincroniza
os arquivos .py no cache do HuggingFace e cria o pipeline sob demanda (lazy
loading), sem executar a carga do modelo na importação do módulo.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Any

import numpy as np
import torch

from core.legacy.audio_spoofing.embedding_utils import (
    aggregate_embeddings,
    register_df_arena_embedding_hook,
)

# Caminho para o código legado do DF Arena.
_DF_ARENA_DIR = Path(__file__).resolve().parents[4] / "Legados" / "audio" / "DF_ARENA_1B"

_REMOTE_CODE_PY = (
    "backbone.py",
    "configuration_antispoofing.py",
    "conformer.py",
    "feature_extraction_antispoofing.py",
    "modeling_antispoofing.py",
    "pipeline_antispoofing.py",
)

_HUB_MODEL_ID = "Speech-Arena-2025/DF_Arena_1B_V_1"

# Global lazy pipeline handle.
_pipeline: Any | None = None


def _model_path() -> str:
    """Resolve the model source: env var, local weights, or HuggingFace Hub."""
    env = os.environ.get("DF_ARENA_MODEL", "").strip()
    if env:
        return env
    local_weights = _DF_ARENA_DIR / "pytorch_model.bin"
    local_safe = list(_DF_ARENA_DIR.glob("*.safetensors"))
    if local_weights.is_file() or local_safe:
        return str(_DF_ARENA_DIR)
    return _HUB_MODEL_ID


def _sync_trust_remote_code_cache(model_dir: str) -> None:
    """Copy local .py model files into the HF transformers modules cache.

    This mirrors the behaviour of detector.py so that trust_remote_code=True
    finds every module (including conformer.py) when loading from a local path.
    """
    model_dir = Path(model_dir).resolve()
    if not model_dir.is_dir():
        return
    if not (model_dir / "config.json").is_file():
        return

    cache_name = model_dir.name
    dest = Path.home() / ".cache" / "huggingface" / "modules" / "transformers_modules" / cache_name
    dest.mkdir(parents=True, exist_ok=True)
    for name in _REMOTE_CODE_PY:
        src = model_dir / name
        if src.is_file():
            shutil.copy2(src, dest / name)
    pycache = dest / "__pycache__"
    if pycache.is_dir():
        shutil.rmtree(pycache, ignore_errors=True)


def _torch_version_major_minor() -> tuple[int, int]:
    ver = torch.__version__.split("+")[0].strip()
    parts = ver.split(".")
    try:
        major = int(parts[0])
    except (ValueError, IndexError):
        major = 0
    try:
        minor = int(parts[1]) if len(parts) > 1 else 0
    except ValueError:
        minor = 0
    return major, minor


def _torch_ge_2_6() -> bool:
    major, minor = _torch_version_major_minor()
    return major > 2 or (major == 2 and minor >= 6)


def _local_snapshot_uses_only_pytorch_bin(model_dir: str) -> bool:
    d = Path(model_dir)
    if not d.is_dir():
        return False
    if not (d / "pytorch_model.bin").is_file():
        return False
    return not any(name.endswith(".safetensors") for name in os.listdir(d))


def _local_dir_has_safetensors(model_dir: str) -> bool:
    d = Path(model_dir)
    if not d.is_dir():
        return False
    return any(name.endswith(".safetensors") for name in os.listdir(d))


def runtime_status() -> tuple[bool, str]:
    """Check whether DF Arena can be loaded.

    Returns (available, reason).
    """
    model_path = _model_path()
    if Path(model_path).is_dir():
        if _local_snapshot_uses_only_pytorch_bin(model_path) and not _torch_ge_2_6():
            ma, mi = _torch_version_major_minor()
            return (
                False,
                f"PyTorch {ma}.{mi} nao pode carregar pytorch_model.bin; necessario PyTorch>=2.6 ou safetensors.",
            )
    return True, ""


def load_pipeline(device: torch.device | str | int | None = None) -> Any:
    """Lazy-load the DF Arena antispoofing pipeline."""
    global _pipeline
    if _pipeline is not None:
        return _pipeline

    from transformers import pipeline

    model_path = _model_path()
    if Path(model_path).is_dir():
        _sync_trust_remote_code_cache(model_path)

    device_id: int | str
    if isinstance(device, torch.device):
        device_id = 0 if device.type == "cuda" else -1
    elif isinstance(device, int):
        device_id = device
    elif isinstance(device, str):
        device_id = 0 if device.lower() == "cuda" else -1
    else:
        device_id = 0 if torch.cuda.is_available() else -1

    model_kwargs: dict[str, Any] = {"dtype": torch.float32}
    if _local_dir_has_safetensors(model_path):
        model_kwargs["use_safetensors"] = True

    _pipeline = pipeline(
        "antispoofing",
        model=model_path,
        trust_remote_code=True,
        device=device_id,
        model_kwargs=model_kwargs,
    )
    return _pipeline


SAMPLE_RATE = 16000
WINDOW_SECONDS = 4.0

# Limiar de incerteza: se ambas as probabilidades forem abaixo deste valor,
# a decisão agregada é classificada como "uncertain".
UNCERTAINTY_THRESHOLD = 0.65


def _logits_from_result(result: dict[str, Any]) -> tuple[float, float]:
    """Extract (spoof_logit, bonafide_logit) from DF Arena pipeline result."""
    logits = result.get("logits", [[0.0, 0.0]])
    if isinstance(logits, (list, tuple)) and len(logits) > 0:
        logits = logits[0]
    spoof_logit = float(logits[0])
    bonafide_logit = float(logits[1])
    return spoof_logit, bonafide_logit


def _softmax(logits: np.ndarray) -> np.ndarray:
    exp = np.exp(logits - np.max(logits))
    return exp / np.sum(exp)


def _split_audio(audio: np.ndarray, window_samples: int, stride_samples: int) -> list[tuple[int, np.ndarray]]:
    """Return list of (start_sample, window_audio) non-overlapping windows."""
    windows: list[tuple[int, np.ndarray]] = []
    total = len(audio)
    start = 0
    while start < total:
        end = min(start + window_samples, total)
        window = audio[start:end]
        windows.append((start, window))
        if end == total:
            break
        start += stride_samples
    return windows


def _pipeline_device(pipe: Any) -> torch.device:
    device = getattr(pipe, "device", None)
    if isinstance(device, torch.device):
        return device
    if isinstance(device, int):
        return torch.device("cuda" if device >= 0 else "cpu")
    if isinstance(device, str):
        return torch.device(device)
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def _infer_df_arena_window(
    pipe: Any,
    window: np.ndarray,
    *,
    return_embedding: bool = False,
) -> tuple[tuple[float, float], np.ndarray | None]:
    if not return_embedding:
        result = pipe(window)
        if result is None:
            raise RuntimeError("DF Arena retornou None")
        spoof_logit, bonafide_logit = _logits_from_result(result)
        return (spoof_logit, bonafide_logit), None

    backbone = pipe.model.backbone
    device_obj = _pipeline_device(pipe)
    hook, store = register_df_arena_embedding_hook(backbone)
    try:
        wav = torch.tensor(window.astype(np.float32), dtype=torch.float32, device=device_obj)
        with torch.no_grad():
            logits = backbone(wav)
        if isinstance(logits, (list, tuple)):
            logits = logits[0]
        logits_np = logits.detach().cpu().numpy().reshape(-1)
        spoof_logit = float(logits_np[0])
        bonafide_logit = float(logits_np[1]) if logits_np.size > 1 else 0.0
        if not store:
            raise RuntimeError("DF Arena embedding hook não capturou saída da penúltima camada")
        return (spoof_logit, bonafide_logit), store[0].astype(np.float32)
    finally:
        hook.remove()


def infer_df_arena_windows(
    audio: np.ndarray,
    sr: int,
    *,
    window_seconds: float = WINDOW_SECONDS,
    device: torch.device | str | int | None = None,
    return_embedding: bool = False,
) -> dict[str, Any]:
    """Run DF Arena 1B on 4-second windows and aggregate by mean of logits.

    Args:
        audio: 1-D numpy array of audio samples.
        sr: sample rate of the audio. Will be resampled to 16 kHz internally
            by librosa inside the DF Arena pipeline.
        window_seconds: length of each analysis window in seconds.
        device: torch device to use; if None, lets the legacy pipeline decide.

    Returns:
        Dictionary with:
        - "windows": list of per-window results with keys:
            - "start_seconds": window start time
            - "center_seconds": window center time
            - "duration_seconds": actual window duration (may be shorter for the last window)
            - "spoof_logit", "bonafide_logit": raw logits
            - "spoof_prob", "bonafide_prob": softmax probabilities
        - "aggregated": dict with aggregated logits and probabilities
        - "window_count": number of windows
        - "inference_device": device label string
    """
    ok, reason = runtime_status()
    if not ok:
        raise RuntimeError(f"DF Arena nao disponivel: {reason}")

    pipe = load_pipeline(device=device)

    if sr != SAMPLE_RATE:
        import librosa
        audio = librosa.resample(audio.astype(np.float32), orig_sr=sr, target_sr=SAMPLE_RATE)

    window_samples = int(SAMPLE_RATE * window_seconds)
    stride_samples = window_samples

    windows = _split_audio(audio, window_samples, stride_samples)
    window_results: list[dict[str, Any]] = []

    spoof_logits: list[float] = []
    bonafide_logits: list[float] = []
    window_embeddings: list[np.ndarray] = []

    for start, window in windows:
        window = window.astype(np.float32)
        (spoof_logit, bonafide_logit), embedding = _infer_df_arena_window(
            pipe, window, return_embedding=return_embedding
        )
        if return_embedding and embedding is not None:
            window_embeddings.append(embedding)
        probs = _softmax(np.array([spoof_logit, bonafide_logit]))

        window_results.append({
            "start_seconds": round(start / SAMPLE_RATE, 3),
            "center_seconds": round((start + len(window) / 2) / SAMPLE_RATE, 3),
            "duration_seconds": round(len(window) / SAMPLE_RATE, 3),
            "spoof_logit": round(spoof_logit, 6),
            "bonafide_logit": round(bonafide_logit, 6),
            "spoof_prob": round(float(probs[0]), 6),
            "bonafide_prob": round(float(probs[1]), 6),
        })

        spoof_logits.append(spoof_logit)
        bonafide_logits.append(bonafide_logit)

    if not spoof_logits:
        raise RuntimeError("Nenhuma janela de audio gerada")

    agg_spoof_logit = float(np.mean(spoof_logits))
    agg_bonafide_logit = float(np.mean(bonafide_logits))
    agg_probs = _softmax(np.array([agg_spoof_logit, agg_bonafide_logit]))

    spoof_prob = float(agg_probs[0])
    bonafide_prob = float(agg_probs[1])
    # Decision rule:
    # - spoof_prob > 65%  -> Spoof
    # - bonafide_prob > 65% -> Bonafide
    # - otherwise (both <= 65%) -> Uncertain
    if spoof_prob > UNCERTAINTY_THRESHOLD:
        label = "spoof"
    elif bonafide_prob > UNCERTAINTY_THRESHOLD:
        label = "bonafide"
    else:
        label = "uncertain"

    inference_device = "cpu"
    if device is not None:
        inference_device = str(device)
    elif torch.cuda.is_available():
        inference_device = "cuda"

    result: dict[str, Any] = {
        "windows": window_results,
        "aggregated": {
            "spoof_logit": round(agg_spoof_logit, 6),
            "bonafide_logit": round(agg_bonafide_logit, 6),
            "spoof_prob": round(spoof_prob, 6),
            "bonafide_prob": round(bonafide_prob, 6),
            "label": label,
        },
        "window_count": len(window_results),
        "inference_device": inference_device,
    }
    if return_embedding:
        result["embedding"] = aggregate_embeddings(window_embeddings)
        result["embedding_dim"] = int(result["embedding"].shape[0])
    return result
