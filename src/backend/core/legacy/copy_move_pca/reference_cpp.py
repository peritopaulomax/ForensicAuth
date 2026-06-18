"""Line-faithful Python port of Peritus CopyMovePCA (filter.cpp) for equivalence checks."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from core.legacy.copy_move_pca.cpp_sort import std_sort_indices
from core.legacy.copy_move_pca.numba_kernels import (
    quantize_lex_keys,
    vectorize_blocks,
    vote_displacements,
)
from core.legacy.copy_move_pca.peritus_mark import build_peritus_colors, mark_peritus_corners

# Legacy subprocess sort fallback (if .so not built)
_SORT_BIN = Path(__file__).resolve().parents[5] / "tools" / "copy_move_pca_sort"


def _std_sort_indices(keys: np.ndarray) -> np.ndarray:
    """std::sort — in-process .so preferred, subprocess fallback."""
    try:
        return std_sort_indices(keys)
    except OSError:
        pass
    import struct
    import subprocess
    import tempfile

    nb = keys.shape[0]
    if _SORT_BIN.is_file():
        with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as handle:
            handle.write(struct.pack("i", nb))
            handle.write(keys.astype(np.float64).tobytes())
            keys_path = handle.name
        out_path = keys_path + ".sorted"
        try:
            subprocess.run([str(_SORT_BIN), keys_path, out_path], check=True, capture_output=True)
            return np.fromfile(out_path, dtype=np.int32, count=nb, offset=4)
        finally:
            Path(keys_path).unlink(missing_ok=True)
            Path(out_path).unlink(missing_ok=True)
    return np.argsort(keys, kind="heapsort").astype(np.int32)


def run_copy_move_pca_reference(
    gray: np.ndarray,
    *,
    b: int = 7,
    n_comp: float = 0.75,
    nn: int = 2,
    q: int = 256,
    nf: int = 128,
    nd: int = 16,
    morph: bool = True,
    alpha_mask: bool = False,
) -> dict:
    """Execute CopyMovePCA exactly as filter.cpp (Peritus-faithful, parallel Numba/OpenCV/BLAS)."""
    if gray.ndim == 3:
        gray = cv2.cvtColor(gray, cv2.COLOR_BGR2GRAY)

    linhas, colunas = gray.shape[:2]
    b2 = b * b
    nb = (linhas - b + 1) * (colunas - b + 1)
    nt = int(round(b2 * n_comp))
    stride = linhas - b + 1
    window = nb - nn + 1

    imagem = gray.astype(np.float32, copy=False)
    dados = vectorize_blocks(imagem, b, linhas, colunas, b2, nb)

    mean, eigenvectors = cv2.PCACompute(dados, mean=None, maxComponents=nt)
    g = cv2.PCAProject(dados, mean, eigenvectors)

    b_keys = quantize_lex_keys(g.astype(np.float64, copy=False), nt, q, float(np.max(g)))

    p_ind = _std_sort_indices(b_keys)

    md, dir_arr, p_desloc_arr, n_desloc = vote_displacements(
        p_ind.astype(np.int32), linhas, colunas, b, nn, nf, nd, nb
    )
    p_desloc_list = [int(p_desloc_arr[i]) for i in range(n_desloc)]
    dest_r = np.zeros((linhas, colunas), dtype=np.uint8)
    dest_g = np.zeros((linhas, colunas), dtype=np.uint8)
    dest_b = np.zeros((linhas, colunas), dtype=np.uint8)

    if n_desloc > 0:
        p_desloc_np = p_desloc_arr[:n_desloc].copy()
        cr, cg, cb = build_peritus_colors(n_desloc, nn, alpha_mask)
        mark_peritus_corners(
            dest_r,
            dest_g,
            dest_b,
            md,
            dir_arr,
            p_desloc_np,
            cr,
            cg,
            cb,
            linhas,
            colunas,
            b,
            nn,
            nb,
            alpha_mask,
        )

    if alpha_mask:
        dest_alpha = cv2.bitwise_not(dest_r)
        dest = cv2.merge([dest_b, dest_g, dest_r, dest_alpha])
    else:
        dest = cv2.merge([dest_b, dest_g, dest_r])

    if morph:
        morph_size = b // 2
        ksize = 2 * morph_size + 1
        element = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, (ksize, ksize), (morph_size, morph_size)
        )
        dest = cv2.morphologyEx(dest, cv2.MORPH_CLOSE, element)
        dest = cv2.morphologyEx(dest, cv2.MORPH_OPEN, element)

    if morph:
        mask = np.max(dest, axis=2).astype(np.uint8)
        mask = (mask > 0).astype(np.uint8) * 255
    else:
        mask = np.maximum(np.maximum(dest_r, dest_g), dest_b)

    unique = []
    seen: set[int] = set()
    for d in p_desloc_list:
        if d not in seen:
            seen.add(d)
            unique.append(d)

    return {
        "mask": mask,
        "colored_bgr": dest if not alpha_mask else cv2.merge([dest_b, dest_g, dest_r]),
        "clone_regions_detected": len(unique),
        "clone_displacements_raw": n_desloc,
        "unique_displacements": unique,
        "p_ind": p_ind,
        "b_keys": b_keys,
    }
