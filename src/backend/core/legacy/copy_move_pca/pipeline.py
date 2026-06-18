"""Copy-Move PCA pipeline (Popescu & Farid 2004 / Peritus INC port)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

import cv2
import numpy as np

from core.legacy.copy_move_pca.parallel_config import configure_copy_move_parallelism
from core.legacy.copy_move_pca.reference_cpp import run_copy_move_pca_reference

ProgressFn = Optional[Callable[[int, str], None]]

DEFAULT_PARAMS: dict = {
    "b": 7,
    "n_comp": 0.75,
    "nn": 2,
    "q": 256,
    "nf": 128,
    "nd": 16,
    "morph": True,
    "alpha_mask": False,
    "max_side": 0,
    "mem_budget_bytes": 0,
}

MEM_BYTES_PER_BLOCK = 4  # float32 in dados matrix (dominant)


@dataclass
class CopyMovePcaParams:
    b: int = 7
    n_comp: float = 0.75
    nn: int = 2
    q: int = 256
    nf: int = 128
    nd: int = 16
    morph: bool = True
    alpha_mask: bool = False
    max_side: int = 0
    mem_budget_bytes: int = 0
    region: tuple[int, int, int, int] | None = None  # x, y, w, h

    @classmethod
    def from_dict(cls, d: dict | None) -> "CopyMovePcaParams":
        d = d or {}
        region = d.get("region")
        if region is not None and isinstance(region, (list, tuple)) and len(region) == 4:
            region = tuple(int(v) for v in region)
        else:
            region = None
        return cls(
            b=int(d.get("b", DEFAULT_PARAMS["b"])),
            n_comp=float(d.get("n_comp", DEFAULT_PARAMS["n_comp"])),
            nn=int(d.get("nn", DEFAULT_PARAMS["nn"])),
            q=int(d.get("q", DEFAULT_PARAMS["q"])),
            nf=int(d.get("nf", DEFAULT_PARAMS["nf"])),
            nd=int(d.get("nd", DEFAULT_PARAMS["nd"])),
            morph=bool(d.get("morph", DEFAULT_PARAMS["morph"])),
            alpha_mask=bool(d.get("alpha_mask", DEFAULT_PARAMS["alpha_mask"])),
            max_side=int(d.get("max_side", DEFAULT_PARAMS["max_side"])),
            mem_budget_bytes=int(d.get("mem_budget_bytes", DEFAULT_PARAMS["mem_budget_bytes"])),
            region=region,
        )


def estimate_memory_bytes(height: int, width: int, b: int) -> int:
    nb = max(0, height - b + 1) * max(0, width - b + 1)
    b2 = b * b
    return nb * b2 * MEM_BYTES_PER_BLOCK


def prepare_gray(
    gray: np.ndarray,
    params: CopyMovePcaParams,
) -> tuple[np.ndarray, float, dict]:
    """Apply ROI crop and optional downscale; return float32 gray + scale factor."""
    meta: dict = {"roi_applied": False, "downscaled": False, "scale": 1.0}
    work = gray
    if params.region is not None:
        x, y, w, h = params.region
        x = max(0, min(x, gray.shape[1] - 1))
        y = max(0, min(y, gray.shape[0] - 1))
        w = max(1, min(w, gray.shape[1] - x))
        h = max(1, min(h, gray.shape[0] - y))
        work = gray[y : y + h, x : x + w].copy()
        meta["roi_applied"] = True
        meta["region"] = (x, y, w, h)

    linhas, colunas = work.shape[:2]
    max_side = max(linhas, colunas)
    if params.max_side > 0 and max_side > params.max_side:
        scale = params.max_side / max_side
        new_w = max(1, int(round(colunas * scale)))
        new_h = max(1, int(round(linhas * scale)))
        work = cv2.resize(work, (new_w, new_h), interpolation=cv2.INTER_AREA)
        meta["downscaled"] = True
        meta["scale"] = scale
        meta["original_work_size"] = (linhas, colunas)

    if work.dtype != np.float32:
        work = work.astype(np.float32)

    return work, float(meta.get("scale", 1.0)), meta


def _report(on_progress: ProgressFn, pct: int, msg: str) -> None:
    if on_progress:
        on_progress(pct, msg)


def run_copy_move_pca(
    gray: np.ndarray,
    params: CopyMovePcaParams | dict | None = None,
    on_progress: ProgressFn = None,
) -> dict:
    """
    Run Copy-Move PCA on a grayscale image (uint8 or float).

    Uses the Peritus-faithful reference path (std::sort + marking loop).
    """
    p = params if isinstance(params, CopyMovePcaParams) else CopyMovePcaParams.from_dict(params)

    if gray.ndim == 3:
        gray = cv2.cvtColor(gray, cv2.COLOR_BGR2GRAY)

    _report(on_progress, 5, "Preparando imagem")
    work, _scale, prep_meta = prepare_gray(gray, p)
    linhas, colunas = work.shape[:2]
    b = p.b
    if linhas < b or colunas < b:
        raise ValueError(f"Imagem {colunas}x{linhas} menor que block size b={b}")

    nb = (linhas - b + 1) * (colunas - b + 1)
    mem_est = estimate_memory_bytes(linhas, colunas, b)
    if p.mem_budget_bytes > 0 and mem_est > p.mem_budget_bytes:
        raise MemoryError(
            f"Estimativa de memoria {mem_est / 1e9:.2f} GB excede limite "
            f"{p.mem_budget_bytes / 1e9:.2f} GB."
        )

    _report(on_progress, 10, "Copy-Move PCA (Peritus)")
    n_threads = configure_copy_move_parallelism()
    result = run_copy_move_pca_reference(
        work,
        b=p.b,
        n_comp=p.n_comp,
        nn=p.nn,
        q=p.q,
        nf=p.nf,
        nd=p.nd,
        morph=p.morph,
        alpha_mask=p.alpha_mask,
    )

    _report(on_progress, 100, "Copy-Move PCA concluido")

    return {
        "mask": result["mask"],
        "colored_bgr": result["colored_bgr"],
        "bgra_overlay": result["colored_bgr"] if p.alpha_mask else None,
        "clone_regions_detected": result["clone_regions_detected"],
        "clone_displacements_raw": result["clone_displacements_raw"],
        "nb_blocks": int(nb),
        "memory_estimate_bytes": mem_est,
        "prep_meta": prep_meta,
        "parallel_threads": n_threads,
        "parameters": {
            "b": b,
            "n_comp": p.n_comp,
            "nn": p.nn,
            "q": p.q,
            "nf": p.nf,
            "nd": p.nd,
            "morph": p.morph,
            "alpha_mask": p.alpha_mask,
        },
    }
