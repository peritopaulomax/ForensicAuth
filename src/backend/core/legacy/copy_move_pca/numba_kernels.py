"""Numba-accelerated kernels for Copy-Move PCA (Popescu & Farid / Peritus port)."""

from __future__ import annotations

import math

import numpy as np
from numba import njit, prange


def vectorize_blocks(imagem: np.ndarray, b: int, linhas: int, colunas: int, b2: int, nb: int) -> np.ndarray:
    """Vectorize b×b sliding blocks — Peritus order j*(linhas-b+1)+i, h*b+k within block."""
    from numpy.lib.stride_tricks import sliding_window_view

    sw = sliding_window_view(imagem, (b, b))
    # Peritus stores block pixels as h*b+k (column h, row k), not NumPy C-order k*b+h.
    return (
        sw.transpose(1, 0, 2, 3)
        .reshape(nb, b, b)
        .transpose(0, 2, 1)
        .reshape(nb, b2)
        .astype(np.float32, copy=False)
    )


def quantize_lex_keys(g: np.ndarray, nt: int, q: int, maximo_g: float) -> np.ndarray:
    """Mixed-radix lexicographic keys B[i] for each block row in G."""
    if g.ndim == 1:
        g = g.reshape(-1, nt)
    base = np.floor(maximo_g / q) + 1.0
    quantized = np.floor(g[:, :nt] / q)
    powers = base ** np.arange(nt, dtype=np.float64)
    return (quantized * powers).sum(axis=1)


def lex_sort_indices(keys: np.ndarray) -> np.ndarray:
    """Unstable lexicographic index sort (Peritus uses std::sort, not stable sort)."""
    return np.argsort(keys, kind="heapsort").astype(np.int32)


def lex_sort_indices_peritus(keys: np.ndarray) -> np.ndarray:
    """Unstable sort for lexicographic keys (Peritus std::sort; heapsort approximates)."""
    return lex_sort_indices(keys)


@njit(parallel=True, cache=True)
def vote_displacements(
    p_ind: np.ndarray,
    linhas: int,
    colunas: int,
    b: int,
    nn: int,
    nf: int,
    nd: int,
    nb: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, int]:
    """Deterministic displacement voting. Returns MD, Dir, p_desloc, n_desloc."""
    stride = linhas - b + 1
    window = nb - nn + 1
    md = np.zeros(nn * window, dtype=np.int32)
    n_dir = max(0, nn - 1)
    dir_arr = np.zeros(n_dir * window, dtype=np.int32)
    cont_size = 2 * (linhas * colunas - 1)
    contador = np.zeros(cont_size, dtype=np.int32)
    p_desloc = np.zeros(10000, dtype=np.int32)
    n_dir_slots = max(0, nn - 1)
    hit_nd = np.zeros(n_dir_slots * window, dtype=np.int8)
    aux_arr = np.zeros(n_dir_slots * window, dtype=np.int32)

    for j in prange(window):
        md[j] = p_ind[j]

    for i in range(1, nn):
        slot_base = (i - 1) * window
        for j in prange(window):
            if p_ind[j + i] > md[j]:
                maior = float(p_ind[j + i])
                menor = float(md[j])
                dir_arr[slot_base + j] = 0
            else:
                menor = float(p_ind[j + i])
                maior = float(md[j])
                dir_arr[slot_base + j] = 1

            distancia = int(
                abs(
                    maior
                    - menor
                    + math.floor(menor / stride) * stride
                    - math.floor(maior / stride) * stride
                )
            )
            distancia += int(math.floor(maior / stride) - math.floor(menor / stride))

            row_m = int(maior - math.floor(maior / stride) * stride)
            row_n = int(menor - math.floor(menor / stride) * stride)

            if row_m < row_n:
                disp = int(menor - maior)
                md[i * window + j] = disp
                if distancia > nd:
                    hit_nd[slot_base + j] = 1
                    aux_arr[slot_base + j] = linhas * colunas - 1 + int(maior - menor)
            else:
                disp = int(maior - menor)
                md[i * window + j] = disp
                if distancia > nd:
                    hit_nd[slot_base + j] = 1
                    aux_arr[slot_base + j] = int(maior - menor)

    n_desloc = 0
    for i in range(1, nn):
        slot_base = (i - 1) * window
        for j in range(window):
            if hit_nd[slot_base + j] == 0:
                continue
            aux = aux_arr[slot_base + j]
            disp = md[i * window + j]
            contador[aux] += 1
            if contador[aux] > nf and n_desloc < 10000:
                p_desloc[n_desloc] = disp
                n_desloc += 1

    return md, dir_arr, p_desloc[:n_desloc], n_desloc


def dedupe_displacements(p_desloc: np.ndarray) -> np.ndarray:
    """Keep first occurrence order of displacement values."""
    seen: set[int] = set()
    out: list[int] = []
    for d in p_desloc:
        val = int(d)
        if val not in seen:
            seen.add(val)
            out.append(val)
    return np.array(out, dtype=np.int32)


@njit(parallel=True, cache=True)
def _mark_all_corners_numba(
    dest_r: np.ndarray,
    dest_g: np.ndarray,
    dest_b: np.ndarray,
    md: np.ndarray,
    dir_arr: np.ndarray,
    p_desloc: np.ndarray,
    color_r: np.ndarray,
    color_g: np.ndarray,
    color_b: np.ndarray,
    linhas: int,
    colunas: int,
    b: int,
    nn: int,
    nb: int,
) -> None:
    stride = linhas - b + 1
    window = nb - nn + 1
    max_row = linhas - b + 1
    max_col = colunas - b + 1
    n_desloc = p_desloc.shape[0]

    for k in range(n_desloc):
        disp = p_desloc[k]
        abs_disp = abs(disp)
        cr = color_r[k]
        cg = color_g[k]
        cb = color_b[k]
        for i in range(1, nn):
            for j in prange(window):
                if md[i * window + j] != disp:
                    continue
                d = dir_arr[(i - 1) * window + j]
                base_idx = md[j]
                coord = base_idx - d * abs_disp
                jj = int(math.floor(coord / stride))
                ii = int(coord - jj * stride)
                if 0 <= ii < max_row and 0 <= jj < max_col:
                    dest_r[ii, jj] = cr
                    dest_r[ii + b - 1, jj + b - 1] = cr
                    dest_g[ii, jj] = cg
                    dest_g[ii + b - 1, jj + b - 1] = cg
                    dest_b[ii, jj] = cb
                    dest_b[ii + b - 1, jj + b - 1] = cb
                coord2 = base_idx + (1 - d) * abs_disp
                jj = int(math.floor(coord2 / stride))
                ii = int(coord2 - jj * stride)
                if 0 <= ii < max_row and 0 <= jj < max_col:
                    dest_r[ii, jj] = cr
                    dest_r[ii + b - 1, jj + b - 1] = cr
                    dest_g[ii, jj] = cg
                    dest_g[ii + b - 1, jj + b - 1] = cg
                    dest_b[ii, jj] = cb
                    dest_b[ii + b - 1, jj + b - 1] = cb


def mark_all_corners(
    dest_r: np.ndarray,
    dest_g: np.ndarray,
    dest_b: np.ndarray,
    md: np.ndarray,
    dir_arr: np.ndarray,
    p_desloc: np.ndarray,
    n_desloc: int,
    linhas: int,
    colunas: int,
    b: int,
    nn: int,
    nb: int,
    alpha_mask: bool,
    palette: "ColorCycle | None" = None,
    colors: list[tuple[int, int, int]] | None = None,
) -> None:
    """Mark cloned block corners — one color per unique displacement (clone pair)."""
    if n_desloc <= 0:
        return

    color_r = np.empty(n_desloc, dtype=np.int32)
    color_g = np.empty(n_desloc, dtype=np.int32)
    color_b = np.empty(n_desloc, dtype=np.int32)
    for k in range(n_desloc):
        if alpha_mask:
            color_r[k], color_g[k], color_b[k] = 255, 255, 255
        elif colors is not None and k < len(colors):
            color_r[k], color_g[k], color_b[k] = colors[k]
        else:
            from core.legacy.copy_move_pca.palette import ColorCycle

            cycle = palette or ColorCycle()
            color_r[k], color_g[k], color_b[k] = cycle.next_color()

    _mark_all_corners_numba(
        dest_r,
        dest_g,
        dest_b,
        md,
        dir_arr,
        p_desloc[:n_desloc],
        color_r,
        color_g,
        color_b,
        linhas,
        colunas,
        b,
        nn,
        nb,
    )
