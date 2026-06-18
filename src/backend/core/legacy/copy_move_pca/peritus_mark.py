"""Numba-accelerated Peritus-faithful marking (filter.cpp k/i/j loops)."""

from __future__ import annotations

import math

import numpy as np
from numba import njit, prange


@njit(parallel=True, cache=True)
def mark_peritus_corners(
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
    alpha_mask: bool,
) -> None:
    stride = linhas - b + 1
    window = nb - nn + 1
    max_row = linhas - b + 1
    max_col = colunas - b + 1
    n_desloc = p_desloc.shape[0]

    for k in range(n_desloc):
        disp_k = p_desloc[k]
        abs_disp = abs(disp_k)
        for i in range(1, nn):
            slot = k * (nn - 1) + (i - 1)
            if alpha_mask:
                cr = 255
                cg = 255
                cb = 255
            else:
                cr = color_r[slot]
                cg = color_g[slot]
                cb = color_b[slot]

            for j in prange(window):
                if md[i * window + j] != disp_k:
                    continue

                d = dir_arr[(i - 1) * window + j]
                base = md[j]

                coord = base - d * abs_disp
                jj = int(math.floor(coord / stride))
                ii = int(coord - jj * stride)
                if 0 <= ii < max_row and 0 <= jj < max_col:
                    dest_r[ii, jj] = cr
                    dest_r[ii + b - 1, jj + b - 1] = cr
                    dest_g[ii, jj] = cg
                    dest_g[ii + b - 1, jj + b - 1] = cg
                    dest_b[ii, jj] = cb
                    dest_b[ii + b - 1, jj + b - 1] = cb

                coord2 = base + (1 - d) * abs_disp
                jj = int(math.floor(coord2 / stride))
                ii = int(coord2 - jj * stride)
                if 0 <= ii < max_row and 0 <= jj < max_col:
                    dest_r[ii, jj] = cr
                    dest_r[ii + b - 1, jj + b - 1] = cr
                    dest_g[ii, jj] = cg
                    dest_g[ii + b - 1, jj + b - 1] = cg
                    dest_b[ii, jj] = cb
                    dest_b[ii + b - 1, jj + b - 1] = cb


def build_peritus_colors(n_desloc: int, nn: int, alpha_mask: bool) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Precompute Peritus getColor() sequence for each (k, i) at j==0."""
    from core.legacy.copy_move_pca.palette import _CLIST

    n_slots = n_desloc * max(0, nn - 1)
    color_r = np.empty(n_slots, dtype=np.int32)
    color_g = np.empty(n_slots, dtype=np.int32)
    color_b = np.empty(n_slots, dtype=np.int32)
    pos = 1
    for _k in range(n_desloc):
        for _i in range(1, nn):
            slot = _k * (nn - 1) + (_i - 1)
            if alpha_mask:
                color_r[slot], color_g[slot], color_b[slot] = 255, 255, 255
            else:
                color_r[slot] = _CLIST[pos]
                pos += 1
                if pos > 54:
                    pos = 1
                color_g[slot] = _CLIST[pos]
                pos += 1
                if pos > 54:
                    pos = 1
                color_b[slot] = _CLIST[pos]
                pos += 1
                if pos > 54:
                    pos = 1
    return color_r, color_g, color_b
