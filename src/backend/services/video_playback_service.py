"""Serve upright video for HTML5 playback (bake rotation metadata when needed)."""

from __future__ import annotations

import hashlib
import logging
import shutil
import subprocess
import threading
from pathlib import Path

from app.config import get_settings
from core.video_display_orientation import probe_video_display_orientation

logger = logging.getLogger(__name__)

_lock = threading.Lock()


class VideoPlaybackError(Exception):
    """Raised when an upright playback derivative cannot be produced."""


def _cache_dir() -> Path:
    root = Path(get_settings().DERIVATIVES_DIR) / "video_playback"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _source_fingerprint(path: Path) -> str:
    st = path.stat()
    payload = f"{path.resolve()}|{st.st_size}|{st.st_mtime_ns}".encode()
    return hashlib.sha256(payload).hexdigest()[:24]


def _bake_upright(source: Path, dest: Path) -> None:
    if not shutil.which("ffmpeg"):
        raise VideoPlaybackError("ffmpeg ausente no PATH")

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp.mp4")
    if tmp.exists():
        tmp.unlink()

    # Default decoder autorotate applies display matrix / rotate tags into pixels.
    # Clear rotate metadata so browsers do not double-apply.
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(source),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        "-metadata:s:v:0",
        "rotate=0",
        str(tmp),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600, check=False)
    except subprocess.TimeoutExpired as exc:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise VideoPlaybackError("ffmpeg timeout ao normalizar orientacao") from exc

    if proc.returncode != 0 or not tmp.is_file() or tmp.stat().st_size < 32:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        reason = (proc.stderr or proc.stdout or "ffmpeg falhou")[-500:]
        raise VideoPlaybackError(f"Falha ao normalizar orientacao do video: {reason}")

    tmp.replace(dest)


def resolve_playback_path(source: Path) -> tuple[Path, dict]:
    """Return (path_to_serve, orientation_info).

    When rotation metadata is present, return a cached upright re-encode.
    Otherwise return the original evidence file.
    """
    info = probe_video_display_orientation(source)
    rotation = int(info.get("rotation_degrees") or 0)
    info = {**info, "baked": False, "playback": "original"}

    if not info.get("available") or rotation == 0:
        return source, info

    cache_path = _cache_dir() / f"{_source_fingerprint(source)}_r{rotation}.mp4"
    with _lock:
        if not cache_path.is_file():
            logger.info(
                "Gerando preview de playback upright (rotate=%s) para %s",
                rotation,
                source.name,
            )
            _bake_upright(source, cache_path)
    info["baked"] = True
    info["playback"] = "baked"
    return cache_path, info
