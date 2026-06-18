"""Testes de sondagem de metadados de audio."""

import numpy as np
import pytest
from scipy.io import wavfile

from core.legacy.audio.audio_probe import probe_audio_metadata


def test_probe_wav_pcm(tmp_path):
    path = tmp_path / "tone.wav"
    wavfile.write(path, 44100, np.zeros(4410, dtype=np.int16))

    meta = probe_audio_metadata(str(path))

    assert meta["sample_rate_hz"] == 44100
    assert meta["duration_sec"] == pytest.approx(0.1, abs=0.01)
    assert meta["bit_depth"] == 16
    assert meta["codec"] == "PCM"
    assert meta["channels"] == 1


def test_probe_missing_file():
    assert probe_audio_metadata("/caminho/inexistente.wav") == {}
