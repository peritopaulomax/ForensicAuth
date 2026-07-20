#!/usr/bin/env python3
"""Forensically-controlled audio augmentations for LR reference calibration.

Mimics common post-synthesis / distribution conditions:
- mp3_128k      : MP3 recompression at 128 kbps (decode back to WAV 16 kHz mono)
- opus_32k      : Opus at 32 kbps (proxy mensageiro/voz)
- noise_snr_20  : ruído ambiente pink @ 20 dB SNR
- noise_snr_15  : ruído ambiente pink @ 15 dB SNR
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

AUGMENTATIONS: tuple[str, ...] = (
    "mp3_128k",
    "opus_32k",
    "noise_snr_20",
    "noise_snr_15",
)

SAMPLE_RATE = 16000


def augmentation_multiplier() -> int:
    """Original + one row per augmentation."""
    return 1 + len(AUGMENTATIONS)


def _require_ffmpeg() -> str:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg ausente — necessário para mp3_128k e opus_32k")
    return ffmpeg


def _require_ffprobe() -> str:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise RuntimeError("ffprobe ausente — necessário para mp3_128k e opus_32k")
    return ffprobe


def _stable_seed(*parts: str) -> int:
    digest = hashlib.sha256("||".join(parts).encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def _to_mono_float32(audio: np.ndarray) -> np.ndarray:
    arr = np.asarray(audio, dtype=np.float32)
    if arr.ndim > 1:
        arr = arr.mean(axis=1)
    return arr.astype(np.float32, copy=False)


def _resample_if_needed(audio: np.ndarray, sr: int, target_sr: int = SAMPLE_RATE) -> tuple[np.ndarray, int]:
    if sr == target_sr:
        return _to_mono_float32(audio), target_sr
    import librosa

    resampled = librosa.resample(_to_mono_float32(audio), orig_sr=int(sr), target_sr=target_sr)
    return resampled.astype(np.float32), target_sr


def _write_wav(path: Path, audio: np.ndarray, sr: int = SAMPLE_RATE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), _to_mono_float32(audio), int(sr), subtype="PCM_16")


def _read_wav(path: Path) -> tuple[np.ndarray, int]:
    audio, sr = sf.read(str(path), always_2d=False)
    return _to_mono_float32(audio), int(sr)


def _pink_noise(length: int, rng: np.random.Generator) -> np.ndarray:
    white = rng.standard_normal(length).astype(np.float32)
    if length <= 1:
        return white
    # Integrator + normalize — proxy de ruído ambiente de baixa frequência.
    pink = np.cumsum(white)
    peak = float(np.max(np.abs(pink))) or 1.0
    return (pink / peak).astype(np.float32)


def mix_noise_at_snr(
    audio: np.ndarray,
    *,
    snr_db: float,
    seed: int,
) -> tuple[np.ndarray, dict[str, Any]]:
    clean = _to_mono_float32(audio)
    rng = np.random.default_rng(seed)
    noise = _pink_noise(len(clean), rng)
    signal_power = float(np.mean(clean**2)) + 1e-12
    noise_power = float(np.mean(noise**2)) + 1e-12
    target_noise_power = signal_power / (10.0 ** (snr_db / 10.0))
    scale = float(np.sqrt(target_noise_power / noise_power))
    noisy = np.clip(clean + noise * scale, -1.0, 1.0).astype(np.float32)
    params = {
        "noise_type": "pink",
        "snr_db": float(snr_db),
        "seed": int(seed),
        "signal_power": signal_power,
        "noise_power": target_noise_power,
    }
    return noisy, params


def _ffmpeg_codec_roundtrip(
    audio: np.ndarray,
    sr: int,
    *,
    suffix: str,
    codec_args: list[str],
) -> tuple[np.ndarray, int]:
    ffmpeg = _require_ffmpeg()
    clean, out_sr = _resample_if_needed(audio, sr)
    with tempfile.TemporaryDirectory(prefix="va_audio_aug_") as tmp:
        tmp_path = Path(tmp)
        src = tmp_path / "src.wav"
        coded = tmp_path / f"out{suffix}"
        dst = tmp_path / "dst.wav"
        _write_wav(src, clean, out_sr)
        cmd_encode = [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(src),
            *codec_args,
            str(coded),
        ]
        subprocess.run(cmd_encode, check=True)
        cmd_decode = [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(coded),
            "-ac",
            "1",
            "-ar",
            str(SAMPLE_RATE),
            str(dst),
        ]
        subprocess.run(cmd_decode, check=True)
        decoded, decoded_sr = _read_wav(dst)
        return decoded, decoded_sr


def apply_augmentation(
    audio: np.ndarray,
    sr: int,
    aug: str,
    *,
    source_id: str = "",
    source_sha256: str = "",
) -> tuple[np.ndarray, int, dict[str, Any]]:
    if aug not in AUGMENTATIONS:
        raise ValueError(f"Augmentacao desconhecida: {aug}")

    if aug == "mp3_128k":
        out, out_sr = _ffmpeg_codec_roundtrip(
            audio,
            sr,
            suffix=".mp3",
            codec_args=["-codec:a", "libmp3lame", "-b:a", "128k"],
        )
        params = {"codec": "libmp3lame", "bitrate_kbps": 128, "roundtrip": "wav->mp3->wav"}
        return out, out_sr, params

    if aug == "opus_32k":
        out, out_sr = _ffmpeg_codec_roundtrip(
            audio,
            sr,
            suffix=".opus",
            codec_args=["-codec:a", "libopus", "-b:a", "32k", "-application", "voip"],
        )
        params = {"codec": "libopus", "bitrate_kbps": 32, "application": "voip", "roundtrip": "wav->opus->wav"}
        return out, out_sr, params

    clean, out_sr = _resample_if_needed(audio, sr)
    seed = _stable_seed(source_id, source_sha256, aug)
    if aug == "noise_snr_20":
        out, params = mix_noise_at_snr(clean, snr_db=20.0, seed=seed)
        return out, out_sr, params
    if aug == "noise_snr_15":
        out, params = mix_noise_at_snr(clean, snr_db=15.0, seed=seed)
        return out, out_sr, params

    raise ValueError(f"Augmentacao nao implementada: {aug}")


def params_json(params: dict[str, Any]) -> str:
    return json.dumps(params, sort_keys=True, ensure_ascii=False)
