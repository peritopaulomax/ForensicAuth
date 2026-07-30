"""Technique-specific result handlers for display, snapshot and preview endpoints.

The dispatcher below keeps ``analysis.py`` generic: each forensic technique can
register a handler for special result operations without adding technique
branches to the API layer.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict

from fastapi import HTTPException, status
from fastapi.responses import JSONResponse

DisplayHandler = Callable[..., dict[str, Any]]
SnapshotHandler = Callable[[Path, str, bytes], dict[str, Any]]
PreviewHandler = Callable[[Any, Path, dict[str, Any]], dict[str, Any]]

_DISPLAY_HANDLERS: dict[str, DisplayHandler] = {}
_SNAPSHOT_HANDLERS: dict[str, SnapshotHandler] = {}
_PREVIEW_HANDLERS: dict[str, PreviewHandler] = {}


def register_display_handler(technique: str, handler: DisplayHandler) -> None:
    """Register a handler that returns JSON display data for a completed job."""
    _DISPLAY_HANDLERS[technique] = handler


def register_snapshot_handler(technique: str, handler: SnapshotHandler) -> None:
    """Register a handler that stores a client-side snapshot for a completed job."""
    _SNAPSHOT_HANDLERS[technique] = handler


def register_preview_handler(technique: str, handler: PreviewHandler) -> None:
    """Register a handler that reprocesses a preview from cached coefficients."""
    _PREVIEW_HANDLERS[technique] = handler


def has_display_handler(technique: str) -> bool:
    return technique in _DISPLAY_HANDLERS


def has_snapshot_handler(technique: str) -> bool:
    return technique in _SNAPSHOT_HANDLERS


def has_preview_handler(technique: str) -> bool:
    return technique in _PREVIEW_HANDLERS


def load_display_data(technique: str, result_dir: Path, **kwargs: Any) -> dict[str, Any]:
    """Return display data for ``technique`` or raise 404 if unavailable."""
    handler = _DISPLAY_HANDLERS.get(technique)
    if handler is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dados de exibicao nao disponiveis para tecnica {technique}",
        )
    return handler(result_dir, **kwargs)


def store_snapshot(
    technique: str,
    result_dir: Path,
    filename: str,
    data: bytes,
) -> dict[str, Any]:
    """Store a client snapshot for ``technique`` or raise 404/422."""
    handler = _SNAPSHOT_HANDLERS.get(technique)
    if handler is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Snapshot nao disponivel para tecnica {technique}",
        )
    return handler(result_dir, filename, data)


def preview(technique: str, job: Any, result_dir: Path, body: dict[str, Any]) -> dict[str, Any]:
    """Run preview reprocessing for ``technique`` or raise 404."""
    handler = _PREVIEW_HANDLERS.get(technique)
    if handler is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Preview nao disponivel para tecnica {technique}",
        )
    return handler(job, result_dir, body)


def _load_spectrogram_display_npz(result_dir: Path) -> dict[str, Any]:
    import numpy as np

    npz_path = result_dir / "spectrogram_full.npz"
    if not npz_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="spectrogram_full.npz nao encontrado",
        )
    with np.load(npz_path, allow_pickle=False) as archive:
        times = archive["times_display"]
        freqs = archive["frequencies_display"]
        mag = archive["magnitude_db_display"]
        sample_rate = int(archive["sample_rate"]) if "sample_rate" in archive else 0
        n_fft = int(archive["n_fft"]) if "n_fft" in archive else 0
        hop_length = int(archive["hop_length"]) if "hop_length" in archive else 0
        stft_shape = (
            [int(archive["stft_shape"][0]), int(archive["stft_shape"][1])]
            if "stft_shape" in archive
            else [int(mag.shape[0]), int(mag.shape[1])]
        )
        duration_sec = float(archive["duration_sec"]) if "duration_sec" in archive else 0.0
        hop_adjusted = bool(archive["hop_adjusted"]) if "hop_adjusted" in archive else False

    return {
        "times": times.astype(float).tolist(),
        "frequencies": freqs.astype(float).tolist(),
        "magnitude_db": mag.astype(float).tolist(),
        "sample_rate": sample_rate,
        "n_fft": n_fft,
        "hop_length": hop_length,
        "stft_shape": stft_shape,
        "display_shape": [int(mag.shape[0]), int(mag.shape[1])],
        "duration_sec": duration_sec,
        "hop_adjusted": hop_adjusted,
    }


def _load_audio_plot_data(result_dir: Path, panel: str | None = None) -> dict[str, Any]:
    ltas_path = result_dir / "ltas_plot_data.json"
    if ltas_path.exists():
        with open(ltas_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if panel:
            if panel not in data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Painel LTAS '{panel}' invalido (use normal, 6db, sorted, derivative)",
                )
            return data[panel]
        return data

    traces_path = result_dir / "plot_traces.json"
    if not traces_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="plot_traces.json nao encontrado",
        )
    with open(traces_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _store_png_snapshot(result_dir: Path, filename: str, data: bytes) -> dict[str, Any]:
    if len(data) < 32:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="PNG invalido",
        )
    result_dir.mkdir(parents=True, exist_ok=True)
    dest = result_dir / filename
    dest.write_bytes(data)
    return {"artifact_filename": filename, "path": str(dest)}


def _preview_wavelet_noise_residue(
    job: Any,
    result_dir: Path,
    body: dict[str, Any],
) -> dict[str, Any]:
    import cv2

    from forensics.wavelet_noise_residue import reprocess_wavelet_noise_residue_from_npz
    from core.preview_effective import merge_effective_parameters, persist_effective_parameters

    npz_path = result_dir / "wnr_dwt_coefficients.npz"
    if not npz_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Coeficientes DWT nao encontrados — reprocesse a imagem",
        )

    visuals = reprocess_wavelet_noise_residue_from_npz(
        npz_path,
        blocksize=body["blocksize"],
        thr=body["thr"],
        post=body["post"],
        aggregate_cache_dir=result_dir,
    )

    cv2.imwrite(str(result_dir / "overlay.png"), visuals["overlay_bgr"])
    cv2.imwrite(str(result_dir / "colored_overlay.png"), visuals["colored_bgr"])
    cv2.imwrite(str(result_dir / "heatmap.png"), visuals["heatmap"])

    job_result: dict[str, Any] = {}
    result_json = result_dir / "result.json"
    if result_json.is_file():
        try:
            with open(result_json, encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                job_result = loaded
        except (json.JSONDecodeError, OSError):
            job_result = {}

    effective = merge_effective_parameters(
        job,
        job_result,
        override={
            "blocksize": body["blocksize"],
            "thr": body["thr"],
            "post": body["post"],
        },
    )
    persist_effective_parameters(result_dir, effective)

    return {
        "success": True,
        "blocksize": body["blocksize"],
        "thr": body["thr"],
        "post": body["post"],
        "effective_parameters": effective,
    }


# Register built-in handlers -------------------------------------------------

register_display_handler("audio_spectrogram", _load_spectrogram_display_npz)

for _audio_plot_technique in (
    "audio_enf",
    "audio_levels",
    "audio_dc_local",
    "audio_ltas",
):
    register_display_handler(_audio_plot_technique, _load_audio_plot_data)

register_snapshot_handler("audio_spectrogram", _store_png_snapshot)

for _audio_plot_technique in (
    "audio_enf",
    "audio_levels",
    "audio_dc_local",
    "audio_ltas",
):
    register_snapshot_handler(_audio_plot_technique, _store_png_snapshot)

register_preview_handler("wavelet_noise_residue", _preview_wavelet_noise_residue)

# Snapshot filename whitelist for audio-plot overlays.
AUDIO_PLOT_SNAPSHOT_FILENAMES: dict[str, str] = {
    "enf_overlay_snapshot.png": "audio_enf",
    "levels_overlay_snapshot.png": "audio_levels",
    "dc_overlay_snapshot.png": "audio_dc_local",
    "ltas_normal_overlay_snapshot.png": "audio_ltas",
    "ltas_6db_overlay_snapshot.png": "audio_ltas",
    "ltas_sorted_overlay_snapshot.png": "audio_ltas",
    "ltas_derivative_overlay_snapshot.png": "audio_ltas",
}
