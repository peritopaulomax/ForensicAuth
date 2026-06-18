"""Vote map colormap from ZERO.ipynb."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

_cmap1 = plt.get_cmap("tab20")
_cmap2 = plt.get_cmap("tab20b")
_cmap3 = plt.get_cmap("tab20c")
_cmap4 = plt.get_cmap("Set3")


def colorize_votes(votes: np.ndarray) -> np.ndarray:
    """Imagem RGB uint8 colorida por id de voto da grade."""
    v = votes.copy()
    v0 = v == 0
    v4 = v == 4
    v[v0] = 4
    v[v4] = 0

    v2 = _cmap1(v / 20.0)
    v2[v >= 20] = _cmap2((v[v >= 20] - 20) / 20.0)
    v2[v >= 40] = _cmap3((v[v >= 40] - 40) / 20.0)
    v2[v >= 60] = _cmap4((v[v >= 60] - 60) / 20.0)

    colored = (255 * v2[..., :3]).astype(np.uint8)
    colored[votes == -1] = 0
    return colored
