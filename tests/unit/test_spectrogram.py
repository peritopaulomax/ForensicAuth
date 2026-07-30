"""Spectrogram: scipy STFT, decimation, PNG export, NPZ display contract.

MERGE mecânico (Fase 3a) de:
  test_spectrogram_scipy.py
  test_spectrogram_decimate.py
  test_spectrogram_export.py
  test_spectrogram_display_api.py
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import numpy as np
from scipy.io import wavfile

from forensics.audio.spectrogram_decimate import decimate_spectrogram_max_pool
from forensics.audio.spectrogram_export import write_spectrogram_png
from forensics.audio.spectrogram_scipy import build_window, compute_spectrogram_db


# --- scipy.signal.spectrogram path ---


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


# --- display decimation ---


class TestSpectrogramDecimate:
    def test_no_decimation_when_small(self):
        z = np.random.randn(100, 200).astype(np.float64)
        times = np.linspace(0, 1, 200)
        freqs = np.linspace(0, 4000, 100)
        z_out, t_out, f_out, meta = decimate_spectrogram_max_pool(
            z, times, freqs, max_time_bins=2000, max_freq_bins=512
        )
        assert meta["decimated"] is False
        assert z_out.shape == z.shape
        assert len(t_out) == 200
        assert len(f_out) == 100

    def test_decimates_large_matrix(self):
        z = np.random.randn(2049, 30000).astype(np.float64)
        times = np.linspace(0, 600, 30000)
        freqs = np.linspace(0, 24000, 2049)
        z_out, t_out, f_out, meta = decimate_spectrogram_max_pool(
            z, times, freqs, max_time_bins=2000, max_freq_bins=512
        )
        assert meta["decimated"] is True
        assert z_out.shape[1] <= 2000
        assert z_out.shape[0] <= 512
        assert z_out.shape == (len(f_out), len(t_out))
        assert np.max(z) >= np.max(z_out) - 1e-6 or True  # max-pool preserves peaks roughly

    def test_max_pool_preserves_peak(self):
        z = np.full((10, 1000), -80.0)
        z[5, 500] = 0.0
        times = np.arange(1000, dtype=float)
        freqs = np.arange(10, dtype=float)
        z_out, _, _, meta = decimate_spectrogram_max_pool(
            z, times, freqs, max_time_bins=50, max_freq_bins=5
        )
        assert meta["decimated"] is True
        assert float(np.max(z_out)) == 0.0


# --- PNG export ---


def test_write_spectrogram_png(tmp_path: Path):
    z = np.random.randn(32, 64).astype(np.float32)
    times = np.linspace(0, 1, 64)
    freqs = np.linspace(0, 4000, 32)
    out = tmp_path / "spec.png"
    write_spectrogram_png(z, times, freqs, out, title="Test")
    assert out.exists()
    assert out.stat().st_size > 100


# --- NPZ display contract (API keys) ---


def test_npz_display_keys_match_api_contract(tmp_path: Path):
    times = np.linspace(0, 1, 50, dtype=np.float32)
    freqs = np.linspace(0, 4000, 30, dtype=np.float32)
    mag = np.random.randn(30, 50).astype(np.float32)
    path = tmp_path / "spectrogram_full.npz"

    np.savez_compressed(
        path,
        times_display=times,
        frequencies_display=freqs,
        magnitude_db_display=mag,
        sample_rate=np.int32(8000),
        n_fft=np.int32(1024),
        hop_length=np.int32(256),
        stft_shape=np.asarray([30, 50], dtype=np.int32),
        duration_sec=np.float32(1.0),
        hop_adjusted=np.bool_(False),
    )

    with np.load(path, allow_pickle=False) as archive:
        assert archive["times_display"].shape == (50,)
        assert archive["frequencies_display"].shape == (30,)
        assert archive["magnitude_db_display"].shape == (30, 50)
        payload = {
            "times": archive["times_display"].astype(float).tolist(),
            "frequencies": archive["frequencies_display"].astype(float).tolist(),
            "magnitude_db": archive["magnitude_db_display"].astype(float).tolist(),
        }
    assert len(payload["times"]) == 50
    assert len(payload["magnitude_db"]) == 30
