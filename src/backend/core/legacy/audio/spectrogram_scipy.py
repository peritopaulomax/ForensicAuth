"""Espectrograma via scipy.signal.spectrogram."""

from __future__ import annotations

from typing import Callable, Optional, Tuple

import numpy as np
from scipy import signal
from scipy.signal import windows as sp_windows

from core.legacy.audio.audio_prepare import load_audio_array

MAX_TIME_FRAMES = 10_000

ProgressFn = Optional[Callable[[int, str], None]]


def build_window(window_type: str, window_length: int, n_fft: int) -> np.ndarray:
    window_length = max(1, int(window_length))
    n_fft = max(window_length, int(n_fft))

    if window_type == "hamming":
        win = np.hamming(window_length)
    elif window_type == "hanning":
        win = np.hanning(window_length)
    elif window_type == "blackman":
        win = np.blackman(window_length)
    elif window_type == "blackmanharris":
        win = sp_windows.blackmanharris(window_length)
    elif window_type == "kaiser":
        win = np.kaiser(window_length, beta=8.6)
    else:
        win = np.hamming(window_length)

    if window_length < n_fft:
        win = np.pad(win, (0, n_fft - window_length), mode="constant")
    return win.astype(np.float64)


def load_mono_audio(
    audio_path: str, resample_rate: float | None = None
) -> Tuple[np.ndarray, int]:
    sr, data = load_audio_array(audio_path)
    if data.ndim > 1:
        data = data.mean(axis=1)
    if np.issubdtype(data.dtype, np.integer):
        audio = data.astype(np.float32) / np.iinfo(data.dtype).max
    else:
        audio = data.astype(np.float32)

    if resample_rate is not None and int(resample_rate) > 0 and int(resample_rate) != int(sr):
        target = int(resample_rate)
        n_out = max(1, int(round(len(audio) * target / sr)))
        audio = signal.resample(audio, n_out).astype(np.float32)
        sr = target
    return audio, int(sr)


def _report(progress: ProgressFn, pct: int, msg: str) -> None:
    if progress is not None:
        progress(pct, msg)


def compute_spectrogram_db_from_audio(
    audio: np.ndarray,
    sr: int,
    *,
    fft_points: int,
    window_type: str,
    window_size_percent: float,
    progress: ProgressFn = None,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, int, int, int, dict]:
    meta: dict = {"hop_adjusted": False}
    n_fft = 2 ** int(fft_points)
    hop_length = n_fft // 4
    n_samples = len(audio)

    est_frames = max(1, (n_samples - n_fft) // max(1, hop_length) + 1)
    if est_frames > MAX_TIME_FRAMES:
        hop_length = max(hop_length, int(np.ceil(n_samples / MAX_TIME_FRAMES)))
        meta["hop_adjusted"] = True
        meta["hop_length_used"] = hop_length

    window_length = int(n_fft * float(window_size_percent) / 100.0)
    win = build_window(window_type, window_length, n_fft)
    nperseg = len(win)
    noverlap = max(0, nperseg - hop_length)

    _report(progress, 40, f"STFT (n_fft={n_fft}, hop={hop_length})…")
    freqs, times, sxx = signal.spectrogram(
        audio,
        fs=sr,
        window=win,
        nperseg=nperseg,
        noverlap=noverlap,
        nfft=n_fft,
        detrend=False,
        return_onesided=True,
        mode="magnitude",
        scaling="spectrum",
    )

    magnitude = np.abs(sxx).astype(np.float32)
    peak = float(np.max(magnitude)) if magnitude.size else 1.0
    magnitude_db = (20.0 * np.log10(np.maximum(magnitude, 1e-12) / peak)).astype(np.float32)
    meta["shape"] = [int(magnitude_db.shape[0]), int(magnitude_db.shape[1])]
    meta["duration_sec"] = round(n_samples / sr, 2)
    return magnitude_db, times, freqs, sr, n_fft, hop_length, meta


def compute_spectrogram_db(
    audio_path: str,
    *,
    fft_points: int,
    window_type: str,
    window_size_percent: float,
    resample_rate: float | None = None,
    progress: ProgressFn = None,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, int, int, int, dict]:
    _report(progress, 12, "Carregando audio…")
    audio, sr = load_mono_audio(audio_path, resample_rate)
    return compute_spectrogram_db_from_audio(
        audio,
        sr,
        fft_points=fft_points,
        window_type=window_type,
        window_size_percent=window_size_percent,
        progress=progress,
    )
