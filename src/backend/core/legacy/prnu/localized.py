"""PRNU localizado — mapa de correlacao por blocos (PRNU Localizado.ipynb)."""

from __future__ import annotations

from typing import Tuple

import numpy as np
from joblib import Parallel, delayed
from numpy.fft import fft2, ifft2


def correlacao_normalizada_bloco(bloco: np.ndarray, padrao: np.ndarray) -> float:
    assert bloco.shape == padrao.shape, "Bloco e padrao devem ter o mesmo tamanho"
    bloco = bloco.astype(float) - np.mean(bloco)
    padrao = padrao.astype(float) - np.mean(padrao)
    fft_bloco = fft2(bloco)
    fft_padrao = fft2(padrao)
    correlacao = ifft2(fft_bloco * np.conj(fft_padrao)).real
    norma_bloco = np.sqrt(np.sum(bloco**2))
    norma_padrao = np.sqrt(np.sum(padrao**2))
    if norma_bloco == 0 or norma_padrao == 0:
        return 0.0
    return float(correlacao[0, 0] / (norma_bloco * norma_padrao))


def processar_bloco(
    noisex: np.ndarray,
    fingerprint: np.ndarray,
    y_start: int,
    x_start: int,
    tamanho_bloco: int,
) -> float:
    y_end = y_start + tamanho_bloco
    x_end = x_start + tamanho_bloco
    bloco = noisex[y_start:y_end, x_start:x_end]
    padrao = fingerprint[y_start:y_end, x_start:x_end]
    return correlacao_normalizada_bloco(bloco, padrao)


def gerar_mapa_correlacao_blocos_paralelo(
    noisex: np.ndarray,
    fingerprint: np.ndarray,
    tamanho_bloco: int,
    k: int,
    n_jobs: int = 2,
) -> np.ndarray:
    """Mapa espacial de correlacao bloco a bloco (PRNU localizado)."""
    altura, largura = noisex.shape
    passo = tamanho_bloco - k
    num_blocos_v = (altura - k) // passo
    num_blocos_h = (largura - k) // passo
    mapa_correlacao = np.zeros((altura, largura), dtype=np.float64)

    args = [
        (noisex, fingerprint, i * passo, j * passo, tamanho_bloco)
        for i in range(num_blocos_v)
        for j in range(num_blocos_h)
    ]
    resultados = Parallel(n_jobs=n_jobs)(
        delayed(processar_bloco)(*arg) for arg in args
    )
    for idx, (i, j) in enumerate([(i, j) for i in range(num_blocos_v) for j in range(num_blocos_h)]):
        y_start, x_start = i * passo, j * passo
        y_end, x_end = y_start + tamanho_bloco, x_start + tamanho_bloco
        mapa_correlacao[y_start:y_end, x_start:x_end] = resultados[idx]
    return mapa_correlacao


def localized_maps(
    noisex: np.ndarray,
    fingerprint: np.ndarray,
    gray_image: np.ndarray,
    block_half: int = 32,
    overlap_k: int = 50,
    n_jobs: int = 2,
    pos_threshold: float = 0.0,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Retorna mapa bruto, mapa positivo binario e overlay na imagem."""
    tamanho_bloco = 2 * block_half + 1
    mapa = gerar_mapa_correlacao_blocos_paralelo(
        noisex, fingerprint, tamanho_bloco, overlap_k, n_jobs=n_jobs
    )
    mapa_pos = np.where(mapa < float(pos_threshold), 0, 1).astype(np.float32)
    if gray_image.ndim == 3:
        gray = np.mean(gray_image, axis=2)
    else:
        gray = gray_image.astype(np.float32)
    if gray.max() > 1.5:
        gray = gray / 255.0
    overlay = gray * mapa_pos
    return mapa, mapa_pos, overlay
