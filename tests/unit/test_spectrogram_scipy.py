"""Tests for scipy.signal.spectrogram path."""

import os
import tempfile

import numpy as np
from scipy.io import wavfile

from core.legacy.audio.spectrogram_scipy import build_window, compute_spectrogram_db


def test_build_window_pads_to_nfft():
    win = build_window("hamming", window_length=100, n_fft=256)
    assert len(win) == 256


def test_compute_spectrogram_db_shapes():
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        path = f.name
    sr = 8000
    t = np.linspace(0, 1.0, sr)
    wavfile.write(path, sr, (np.sin(2 * np.pi * 440 * t) * 32767).astype(np.int16))
    try:
        mag_db, times, freqs, out_sr, n_fft, hop, meta = compute_spectrogram_db(
            path,
            fft_points=10,
            window_type="hamming",
            window_size_percent=75,
            resample_rate=None,
        )
        assert out_sr == sr
        assert n_fft == 1024
        assert hop == 256
        assert mag_db.ndim == 2
        assert len(times) == mag_db.shape[1]
        assert len(freqs) == mag_db.shape[0]
        assert "shape" in meta
        assert float(np.max(mag_db)) <= 0.0
    finally:
        os.unlink(path)
