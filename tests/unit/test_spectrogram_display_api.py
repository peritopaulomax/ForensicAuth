"""NPZ artefato spectrogram_full — chaves esperadas pelo endpoint de exibicao."""

from pathlib import Path

import numpy as np


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
