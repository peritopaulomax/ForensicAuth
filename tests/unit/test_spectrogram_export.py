"""Export PNG do espectrograma."""

from pathlib import Path

import numpy as np

from core.legacy.audio.spectrogram_export import write_spectrogram_png


def test_write_spectrogram_png(tmp_path: Path):
    z = np.random.randn(32, 64).astype(np.float32)
    times = np.linspace(0, 1, 64)
    freqs = np.linspace(0, 4000, 32)
    out = tmp_path / "spec.png"
    write_spectrogram_png(z, times, freqs, out, title="Test")
    assert out.exists()
    assert out.stat().st_size > 100
