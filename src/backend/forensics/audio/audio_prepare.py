"""Preparacao de audio para analise (residuo estereo, WAV temporario)."""

from __future__ import annotations

import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Tuple

logger = logging.getLogger(__name__)

import numpy as np
import soundfile as sf
from scipy.io import wavfile


def process_stereo_differential_array(
    sample_rate: int, data: np.ndarray, enabled: bool
) -> Tuple[int, np.ndarray]:
    """Residuo diferencial estereo (L-R) para analise de canal."""
    if not enabled:
        return sample_rate, data

    if data.ndim == 1:
        return sample_rate, data
    if data.shape[1] < 2:
        return sample_rate, data

    left_channel = data[:, 0]
    right_channel = data[:, 1]

    if np.issubdtype(data.dtype, np.integer):
        left_int64 = left_channel.astype(np.int64)
        right_int64 = right_channel.astype(np.int64)
        differential_residue = (right_int64 - left_int64) // 2
        min_val, max_val = np.iinfo(data.dtype).min, np.iinfo(data.dtype).max
        differential_residue = np.clip(differential_residue, min_val, max_val)
        differential_residue = differential_residue.astype(data.dtype)
    else:
        differential_residue = (right_channel - left_channel) / 2.0
        differential_residue = np.clip(differential_residue, -1.0, 1.0)

    return sample_rate, differential_residue.reshape(-1, 1)


def load_audio_array(evidence_path: str) -> Tuple[int, np.ndarray]:
    """Carrega audio preservando canais quando possivel."""
    try:
        sr, data = wavfile.read(evidence_path)
        return int(sr), data
    except Exception:
        import librosa

        audio, sr = librosa.load(evidence_path, sr=None, mono=False)
        if audio.ndim == 1:
            data = audio
        else:
            data = (audio.T * (2**15 - 1)).astype(np.int16)
        return int(sr), data


def safe_unlink(path: Path | str | None, *, retries: int = 8, delay_s: float = 0.15) -> None:
    """Remove arquivo temporario; no Windows librosa pode manter o handle aberto brevemente."""
    if path is None:
        return
    p = Path(path)
    if not p.exists():
        return
    last_err: OSError | None = None
    for attempt in range(retries):
        try:
            p.unlink()
            return
        except OSError as exc:
            last_err = exc
            winerr = getattr(exc, "winerror", None)
            if winerr != 32 and exc.errno not in (13, 32):
                raise
            if attempt < retries - 1:
                time.sleep(delay_s * (attempt + 1))
    if last_err is not None:
        logger.warning("Nao foi possivel remover %s: %s", p, last_err)


def prepare_wav_for_analysis(
    evidence_path: str,
    *,
    stereo_diff: bool = False,
    dest_path: Path | None = None,
) -> Tuple[str, Path | None]:
    """
    Retorna caminho WAV normalizado para o pipeline de analise.
    Segundo valor: arquivo temporario a remover apos uso (ou None).

    Se dest_path for informado, grava la (pasta do job) e nao apaga — evita WinError 32.
    """
    sr, data = load_audio_array(evidence_path)
    sr, data = process_stereo_differential_array(sr, data, stereo_diff)

    if not stereo_diff and Path(evidence_path).suffix.lower() in {".wav", ".wave"}:
        try:
            wavfile.read(evidence_path)
            return evidence_path, None
        except Exception:
            pass

    if dest_path is not None:
        target = dest_path
        target.parent.mkdir(parents=True, exist_ok=True)
        if np.issubdtype(data.dtype, np.integer):
            sf.write(str(target), data, sr)
        else:
            sf.write(str(target), data.astype(np.float32), sr)
        return str(target), None

    fd, tmp_name = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        if np.issubdtype(data.dtype, np.integer):
            sf.write(str(tmp), data, sr)
        else:
            sf.write(str(tmp), data.astype(np.float32), sr)
    except Exception:
        safe_unlink(tmp)
        raise
    return str(tmp), tmp
