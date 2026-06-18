"""Tests for audio temp file handling (Windows-safe)."""

import os
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.io import wavfile

from core.legacy.audio.audio_prepare import prepare_wav_for_analysis, safe_unlink


def test_mkstemp_temp_can_be_removed_after_librosa_style_read():
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        path = f.name
    sr = 8000
    t = np.linspace(0, 0.5, sr // 2)
    wavfile.write(path, sr, (np.sin(2 * np.pi * 440 * t) * 32767).astype(np.int16))

    wav_path, tmp = prepare_wav_for_analysis(path, stereo_diff=False)
    assert tmp is None
    assert wav_path == path

    import librosa

    librosa.load(wav_path, sr=None, mono=True)
    os.unlink(path)


def test_temp_wav_unlinks_after_use():
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        wav_src = f.name.replace(".mp3", ".wav")
    sr = 8000
    signal = (np.random.randn(sr).astype(np.float32) * 0.1)
    sf.write(wav_src, signal, sr)
    try:
        wav_path, tmp = prepare_wav_for_analysis(wav_src, stereo_diff=True)
        assert tmp is not None
        assert tmp.exists()
        import librosa

        librosa.load(wav_path, sr=None, mono=True)
        safe_unlink(tmp)
        assert not tmp.exists()
    finally:
        Path(wav_src).unlink(missing_ok=True)
