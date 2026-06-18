"""Decimacao max-pool do espectrograma para exibicao Plotly (performance)."""

from __future__ import annotations

import numpy as np

DEFAULT_MAX_TIME_BINS = 2000
DEFAULT_MAX_FREQ_BINS = 512


def decimate_spectrogram_max_pool(
    magnitude_db: np.ndarray,
    times: np.ndarray,
    freqs: np.ndarray,
    *,
    max_time_bins: int = DEFAULT_MAX_TIME_BINS,
    max_freq_bins: int = DEFAULT_MAX_FREQ_BINS,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict]:
    """
    Reduz matriz tempo-frequencia para o grafico sem alterar o STFT completo.

    Usa max-pool por bloco para preservar picos de energia (tons, transientes).
    """
    z = np.asarray(magnitude_db, dtype=np.float64)
    times = np.asarray(times, dtype=np.float64)
    freqs = np.asarray(freqs, dtype=np.float64)

    n_rows, n_cols = z.shape
    meta = {
        "decimated": False,
        "full_shape": [int(n_rows), int(n_cols)],
        "display_shape": [int(n_rows), int(n_cols)],
        "row_pool_factor": 1,
        "col_pool_factor": 1,
        "max_time_bins": max_time_bins,
        "max_freq_bins": max_freq_bins,
    }

    if n_cols <= max_time_bins and n_rows <= max_freq_bins:
        return z, times, freqs, meta

    col_factor = max(1, int(np.ceil(n_cols / max_time_bins)))
    row_factor = max(1, int(np.ceil(n_rows / max_freq_bins)))
    n_cols_out = int(np.ceil(n_cols / col_factor))
    n_rows_out = int(np.ceil(n_rows / row_factor))

    pad_rows = n_rows_out * row_factor - n_rows
    pad_cols = n_cols_out * col_factor - n_cols
    pad_value = float(np.nanmin(z)) if z.size else -120.0
    zp = np.pad(z, ((0, pad_rows), (0, pad_cols)), mode="constant", constant_values=pad_value)
    z_out = zp.reshape(n_rows_out, row_factor, n_cols_out, col_factor).max(axis=(1, 3))

    col_centers = np.minimum(np.arange(n_cols_out) * col_factor + col_factor // 2, n_cols - 1)
    row_centers = np.minimum(np.arange(n_rows_out) * row_factor + row_factor // 2, n_rows - 1)
    times_out = times[col_centers]
    freqs_out = freqs[row_centers]

    meta.update(
        {
            "decimated": True,
            "display_shape": [int(n_rows_out), int(n_cols_out)],
            "row_pool_factor": row_factor,
            "col_pool_factor": col_factor,
        }
    )
    return z_out, times_out, freqs_out, meta
