"""Materialize preview artifacts with effective parameters before derivative save."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import numpy as np

from core.plugins.ela_plugin import BASE_ELA_SCALE


def materialize_preview_artifact(
    technique: str,
    result_dir: Path,
    artifact_filename: str,
    effective_parameters: dict[str, Any],
) -> None:
    """Update on-disk artifacts to match effective preview parameters when needed."""
    if technique == "ela" and artifact_filename == "heatmap.png":
        gain = float(effective_parameters.get("gain", 1.0))
        materialize_ela_heatmap(result_dir, gain)
    elif technique == "imdlbenco" and artifact_filename == "mask.png":
        threshold = float(effective_parameters.get("threshold", 0.85))
        materialize_imdl_mask(result_dir, threshold)
    elif technique == "wavelet_noise_residue" and artifact_filename in (
        "heatmap.png",
        "overlay.png",
        "colored_overlay.png",
    ):
        materialize_wavelet_noise_residue(result_dir, effective_parameters)


def materialize_ela_heatmap(result_dir: Path, gain: float) -> None:
    """Apply gain to heatmap_base.png and write heatmap.png (promotable artifact)."""
    gain = max(0.1, min(10.0, float(gain)))
    out_path = result_dir / "heatmap.png"
    base_path = result_dir / "heatmap_base.png"
    if not base_path.is_file():
        if abs(gain - 1.0) < 1e-6 and out_path.is_file():
            return
        if out_path.is_file():
            base_path = out_path
        else:
            raise FileNotFoundError("heatmap_base.png ou heatmap.png nao encontrado para materializar ELA")

    base = cv2.imread(str(base_path), cv2.IMREAD_UNCHANGED)
    if base is None:
        if abs(gain - 1.0) < 1e-6 and out_path.is_file():
            return
        raise ValueError("Falha ao ler heatmap base do ELA")
    if base.ndim == 2:
        diff_est = base.astype(np.float32) / float(BASE_ELA_SCALE)
        scaled = np.clip(diff_est * gain * BASE_ELA_SCALE, 0, 255).astype(np.uint8)
        out = scaled
    else:
        diff_est = base.astype(np.float32) / float(BASE_ELA_SCALE)
        scaled = np.clip(diff_est * gain * BASE_ELA_SCALE, 0, 255).astype(np.uint8)
        out = scaled

    cv2.imwrite(str(result_dir / "heatmap.png"), out)


def materialize_imdl_mask(result_dir: Path, threshold: float) -> None:
    """Binarize score_map.png with threshold and write mask.png."""
    score_path = result_dir / "score_map.png"
    if not score_path.is_file():
        raise FileNotFoundError("score_map.png nao encontrado para materializar mascara IMDL")

    scores = cv2.imread(str(score_path), cv2.IMREAD_GRAYSCALE)
    if scores is None:
        raise ValueError("Falha ao ler score_map.png")

    thr = max(0.0, min(1.0, float(threshold)))
    thr_byte = int(round(thr * 255))
    mask = (scores >= thr_byte).astype(np.uint8) * 255
    cv2.imwrite(str(result_dir / "mask.png"), mask)


def materialize_wavelet_noise_residue(
    result_dir: Path,
    effective_parameters: dict[str, Any],
) -> None:
    """Re-aggregate HH and apply threshold before promoting WNR artifacts."""
    from core.legacy.wavelet_noise_residue import reprocess_wavelet_noise_residue_from_npz

    npz_path = result_dir / "wnr_dwt_coefficients.npz"
    if not npz_path.is_file():
        raise FileNotFoundError(
            "wnr_dwt_coefficients.npz nao encontrado — reprocesse a analise wavelet"
        )

    blocksize = int(effective_parameters.get("blocksize", 3))
    thr = int(effective_parameters.get("thr", 255))
    post = bool(effective_parameters.get("post", True))

    visuals = reprocess_wavelet_noise_residue_from_npz(
        npz_path,
        blocksize=blocksize,
        thr=thr,
        post=post,
        aggregate_cache_dir=result_dir,
    )
    cv2.imwrite(str(result_dir / "overlay.png"), visuals["overlay_bgr"])
    cv2.imwrite(str(result_dir / "colored_overlay.png"), visuals["colored_bgr"])
    cv2.imwrite(str(result_dir / "heatmap.png"), visuals["heatmap"])
