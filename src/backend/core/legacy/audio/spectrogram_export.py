"""Export espectrograma Plotly para PNG (fallback matplotlib)."""

from __future__ import annotations

from pathlib import Path

import numpy as np


def write_spectrogram_png(
    magnitude_db: np.ndarray,
    times: np.ndarray,
    freqs: np.ndarray,
    path: Path,
    *,
    title: str = "Espectrograma",
) -> str:
    """Salva heatmap do espectrograma como PNG."""
    path.parent.mkdir(parents=True, exist_ok=True)
    z = np.asarray(magnitude_db, dtype=np.float64)
    t = np.asarray(times, dtype=np.float64)
    f = np.asarray(freqs, dtype=np.float64)

    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(12, 6.5), dpi=120)
    mesh = ax.pcolormesh(t, f, z, shading="auto", cmap="inferno")
    fig.colorbar(mesh, ax=ax, label="Magnitude (dB)")
    ax.set_xlabel("Tempo (s)")
    ax.set_ylabel("Frequência (Hz)")
    ax.set_title(title)
    fig.tight_layout()
    fig.savefig(str(path), bbox_inches="tight")
    plt.close(fig)
    return str(path)
