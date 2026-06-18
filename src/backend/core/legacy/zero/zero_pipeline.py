"""Pipeline de analise ZERO — orquestra libzero.so_."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import cv2
import numpy as np

from core.legacy.zero.libzero_loader import (
    allocate_meaningful_regions,
    get_ffi,
    get_libzero,
    pointer_from_array,
)
from core.legacy.zero.vote_colormap import colorize_votes

ProgressFn = Optional[Callable[[int, str], None]]


def _prepare_rgb_planar(image_bgr: np.ndarray) -> Tuple[np.ndarray, int, int, int]:
    """BGR uint8/float -> planar C-order (C, H, W) float64."""
    if image_bgr.dtype != np.float64:
        rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB).astype(np.float64)
    else:
        rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)

    h, w, c = rgb.shape
    planar = rgb.transpose((2, 0, 1)).copy(order="C")
    return planar, h, w, c


def _regions_from_c_array(ffi: Any, forged_region: Any, count: int) -> List[Dict[str, Any]]:
    regions: List[Dict[str, Any]] = []
    for i in range(count):
        r = forged_region[i]
        regions.append(
            {
                "x0": int(r.x0),
                "y0": int(r.y0),
                "x1": int(r.x1),
                "y1": int(r.y1),
                "grid_dx": int(r.grid % 8),
                "grid_dy": int(r.grid // 8),
                "grid_index": int(r.grid),
                "lnfa": float(r.lnfa),
            }
        )
    return regions


def run_zero_analysis(
    image_bgr: np.ndarray,
    *,
    include_simulation: bool = False,
    simulation_quality: int = 99,
    on_progress: ProgressFn = None,
) -> Dict[str, Any]:
    """
    Execute steps 1–4 of ZERO.ipynb (+ optional step 5 simulation branch).

    image_bgr: OpenCV BGR image (uint8).
    """
    def prog(pct: int, msg: str) -> None:
        if on_progress:
            on_progress(pct, msg)

    libzero = get_libzero()
    ffi = get_ffi()

    prog(5, "Preparando imagem")
    planar, h, w, c = _prepare_rgb_planar(image_bgr)

    im = np.zeros((h, w), dtype=np.float64)
    im = im.copy(order="C")

    prog(15, "Luminancia (libzero)")
    libzero.rgb2luminance(pointer_from_array(ffi, planar), pointer_from_array(ffi, im), w, h, c)

    prog(30, "Mapa de votos por pixel")
    votes = np.zeros(im.shape, dtype=np.int32)
    libzero.compute_grid_votes_per_pixel(pointer_from_array(ffi, im), pointer_from_array(ffi, votes), w, h)

    colored_votes = colorize_votes(votes)

    prog(50, "Deteccao de grades globais")
    lnfa_grids = np.zeros((8, 8), dtype=np.float64)
    main_grid = int(libzero.detect_global_grids(
        pointer_from_array(ffi, votes), pointer_from_array(ffi, lnfa_grids), w, h
    ))

    significant_grids: List[Dict[str, Any]] = []
    for i in range(64):
        row, col = i // 8, i % 8
        lnfa_val = float(lnfa_grids[row, col])
        if lnfa_val < 0.0:
            significant_grids.append({"dx": col, "dy": row, "lnfa": lnfa_val, "index": i})

    prog(65, "Deteccao de falsificacoes (grade estrangeira)")
    forgery = np.zeros(im.shape, dtype=np.int32)
    forgery_c = np.zeros(im.shape, dtype=np.int32)
    forged_region, forged_region_ptr = allocate_meaningful_regions(ffi, w * h)
    forgery_found = int(
        libzero.detect_forgeries(
            pointer_from_array(ffi, votes),
            pointer_from_array(ffi, forgery),
            pointer_from_array(ffi, forgery_c),
            forged_region_ptr,
            w,
            h,
            main_grid,
            63,
        )
    )
    regions_pass1 = _regions_from_c_array(ffi, forged_region, forgery_found)
    forgery_result = forgery_c.copy()

    colored_votes_sim: Optional[np.ndarray] = None
    regions_pass2: List[Dict[str, Any]] = []
    forgery_found2 = 0

    if include_simulation and main_grid > -1:
        prog(75, "Simulacao JPEG e segunda passagem")
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            sim_path = tmp.name
        try:
            rgb_u8 = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
            from PIL import Image

            pil_image = Image.fromarray(rgb_u8)
            pil_image.save(sim_path, format="JPEG", quality=int(simulation_quality))

            sim_bgr = cv2.imread(sim_path)
            if sim_bgr is not None:
                pil_planar, h2, w2, c2 = _prepare_rgb_planar(sim_bgr)
                img = np.zeros((h2, w2), dtype=np.float64)
                libzero.rgb2luminance(
                    pointer_from_array(ffi, pil_planar),
                    pointer_from_array(ffi, img),
                    w2,
                    h2,
                    c2,
                )

                votes2 = np.zeros(img.shape, dtype=np.int32)
                libzero.compute_grid_votes_per_pixel(
                    pointer_from_array(ffi, img), pointer_from_array(ffi, votes2), w2, h2
                )

                for gi in range(64):
                    if lnfa_grids[gi // 8, gi % 8] < 0.0:
                        votes2[votes == gi] = -1

                colored_votes_sim = colorize_votes(votes2)

                forgery2 = np.zeros(img.shape, dtype=np.int32)
                forgery_c2 = np.zeros(img.shape, dtype=np.int32)
                forged_region2, forged_region2_ptr = allocate_meaningful_regions(
                    ffi, w2 * h2
                )
                forgery_found2 = int(
                    libzero.detect_forgeries(
                        pointer_from_array(ffi, votes2),
                        pointer_from_array(ffi, forgery2),
                        pointer_from_array(ffi, forgery_c2),
                        forged_region2_ptr,
                        w2,
                        h2,
                        -1,
                        0,
                    )
                )
                regions_pass2 = _regions_from_c_array(ffi, forged_region2, forgery_found2)
                if forgery_found2 > 0:
                    combined = forgery_c.astype(np.float64) + 0.5 * forgery_c2.astype(np.float64)
                    forgery_result = np.clip(combined, 0, 255).astype(np.int32)
        finally:
            Path(sim_path).unlink(missing_ok=True)

    prog(95, "Finalizando")

    main_grid_dx = main_grid % 8 if main_grid >= 0 else -1
    main_grid_dy = main_grid // 8 if main_grid >= 0 else -1

    return {
        "width": w,
        "height": h,
        "main_grid": main_grid,
        "main_grid_dx": main_grid_dx,
        "main_grid_dy": main_grid_dy,
        "main_grid_detected": main_grid > -1,
        "main_grid_misaligned": main_grid > 0,
        "lnfa_grids": lnfa_grids.tolist(),
        "significant_grids": significant_grids,
        "colored_votes": colored_votes,
        "colored_votes_simulated": colored_votes_sim,
        "forgery_mask": forgery_result,
        "forgery_found_pass1": forgery_found,
        "forgery_found_pass2": forgery_found2,
        "forged_regions_pass1": regions_pass1,
        "forged_regions_pass2": regions_pass2,
    }
