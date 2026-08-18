"""Display orientation for HTML5 video playback (rotation metadata)."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def normalize_rotation_degrees(value: Any) -> int:
    """Normalize to {0, 90, 180, 270} (clockwise CSS degrees for upright display)."""
    try:
        deg = int(round(float(value)))
    except (TypeError, ValueError):
        return 0
    deg %= 360
    if deg < 0:
        deg += 360
    # Snap near-misses from float displaymatrix values
    for candidate in (0, 90, 180, 270):
        if abs(deg - candidate) <= 1 or abs(deg - candidate - 360) <= 1:
            return candidate
    return 0


def rotation_from_ffprobe_stream(stream: dict[str, Any]) -> int:
    """Extract clockwise display rotation from one ffprobe video stream dict."""
    tags = stream.get("tags") or {}
    if "rotate" in tags:
        return normalize_rotation_degrees(tags["rotate"])

    for side in stream.get("side_data_list") or []:
        if not isinstance(side, dict):
            continue
        if "rotation" in side:
            # ffprobe Display Matrix reports counter-clockwise degrees; CSS needs clockwise.
            return normalize_rotation_degrees(-float(side["rotation"]))
    return 0


def probe_video_display_orientation(path: str | Path) -> dict[str, Any]:
    """Return coded size + clockwise rotation for upright playback.

    Keys: available, rotation_degrees, coded_width, coded_height, reason (optional).
    """
    path = Path(path)
    if not path.is_file():
        return {
            "available": False,
            "rotation_degrees": 0,
            "coded_width": None,
            "coded_height": None,
            "reason": "arquivo ausente",
        }
    if not shutil.which("ffprobe"):
        return {
            "available": False,
            "rotation_degrees": 0,
            "coded_width": None,
            "coded_height": None,
            "reason": "ffprobe ausente no PATH",
        }

    cmd = [
        "ffprobe",
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_streams",
        "-select_streams",
        "v:0",
        str(path),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=False)
    except subprocess.TimeoutExpired:
        return {
            "available": False,
            "rotation_degrees": 0,
            "coded_width": None,
            "coded_height": None,
            "reason": "ffprobe timeout",
        }
    except Exception as exc:
        return {
            "available": False,
            "rotation_degrees": 0,
            "coded_width": None,
            "coded_height": None,
            "reason": str(exc),
        }

    if proc.returncode != 0:
        return {
            "available": False,
            "rotation_degrees": 0,
            "coded_width": None,
            "coded_height": None,
            "reason": (proc.stderr or proc.stdout or "ffprobe falhou")[:300],
        }

    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        return {
            "available": False,
            "rotation_degrees": 0,
            "coded_width": None,
            "coded_height": None,
            "reason": f"JSON ffprobe invalido: {exc}",
        }

    streams = data.get("streams") or []
    stream = streams[0] if streams else {}
    width = stream.get("width")
    height = stream.get("height")
    try:
        coded_width = int(width) if width is not None else None
    except (TypeError, ValueError):
        coded_width = None
    try:
        coded_height = int(height) if height is not None else None
    except (TypeError, ValueError):
        coded_height = None

    return {
        "available": True,
        "rotation_degrees": rotation_from_ffprobe_stream(stream),
        "coded_width": coded_width,
        "coded_height": coded_height,
    }


def heatmap_export_rotation_degrees(
    *,
    metadata_rotation: int,
    coded_width: int | None,
    coded_height: int | None,
) -> int:
    """CW degrees to rotate a VideoFACT heatmap for upright human viewing.

    Inference matches the vendor (ignores container rotation; only special-cases
    decoded H>W). Landscape-coded clips with rotate/displaymatrix stay sideways
    in model space — rotate export/display only, never model inputs/scores.
    """
    rot = normalize_rotation_degrees(metadata_rotation)
    if rot == 0:
        return 0
    if coded_width and coded_height and coded_height > coded_width:
        # Portrait pixels already pass through vendor transpose+vflip.
        return 0
    return rot


def css_rotation_if_needed(
    *,
    metadata_rotation: int,
    coded_width: int | None,
    coded_height: int | None,
    displayed_width: int,
    displayed_height: int,
) -> int:
    """Return CSS clockwise degrees to apply, or 0 if the browser already oriented.

    For 90/270, swapped display size vs coded size means the browser applied the matrix.
    For 180, dimensions stay the same — apply CSS only when metadata says 180 and the
    browser reports coded size (cannot detect double-apply; prefer metadata).
    """
    rot = normalize_rotation_degrees(metadata_rotation)
    if rot == 0:
        return 0
    if not coded_width or not coded_height or not displayed_width or not displayed_height:
        return rot

    tol = max(2, int(0.02 * max(coded_width, coded_height)))
    swapped = (
        abs(displayed_width - coded_height) <= tol
        and abs(displayed_height - coded_width) <= tol
    )
    as_coded = (
        abs(displayed_width - coded_width) <= tol
        and abs(displayed_height - coded_height) <= tol
    )

    if rot in (90, 270):
        if swapped:
            return 0
        if as_coded:
            return rot
        # Ambiguous sizes (letterboxing / SAR): trust metadata
        return rot

    # 180° keeps the same width/height; cannot detect browser autorotate.
    # Callers that need a deterministic upright stream should bake via ffmpeg
    # (see video_playback_service) instead of CSS.
    return 0
