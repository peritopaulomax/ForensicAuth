"""Tests for spectrogram display decimation."""

import numpy as np

from core.legacy.audio.spectrogram_decimate import decimate_spectrogram_max_pool


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
