"""Unit tests for audio LR channel augmentations and stratified sampling."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src" / "backend"))

from audio_lr_augmentation import (  # noqa: E402
    AUGMENTATIONS,
    apply_augmentation,
    augmentation_multiplier,
    mix_noise_at_snr,
)
from core.audio_spoofing_lr_reference import (  # noqa: E402
    AUGMENTATION_MULTIPLIER,
    AUGMENTATION_NAMES,
    _sample_stratified,
)


class TestAudioLrAugmentation:
    def test_augmentation_names_and_multiplier(self):
        assert AUGMENTATIONS == AUGMENTATION_NAMES
        assert augmentation_multiplier() == AUGMENTATION_MULTIPLIER == 5

    def test_noise_snr_20(self):
        rng = np.random.default_rng(42)
        audio = rng.standard_normal(16000).astype(np.float32) * 0.1
        out, params = mix_noise_at_snr(audio, snr_db=20.0, seed=123)
        assert out.shape == audio.shape
        assert params["snr_db"] == 20.0
        assert params["noise_type"] == "pink"

    def test_noise_snr_15(self):
        rng = np.random.default_rng(7)
        audio = rng.standard_normal(8000).astype(np.float32) * 0.05
        out, sr, params = apply_augmentation(
            audio,
            16000,
            "noise_snr_15",
            source_id="clip001",
            source_sha256="abc123",
        )
        assert out.shape == audio.shape
        assert sr == 16000
        assert params["snr_db"] == 15.0

    def test_noise_is_deterministic_for_same_source(self):
        rng = np.random.default_rng(99)
        audio = rng.standard_normal(4000).astype(np.float32) * 0.2
        out_a, _, _ = apply_augmentation(audio, 16000, "noise_snr_20", source_id="x", source_sha256="sha")
        out_b, _, _ = apply_augmentation(audio, 16000, "noise_snr_20", source_id="x", source_sha256="sha")
        np.testing.assert_array_equal(out_a, out_b)

    @pytest.mark.skipif(
        not Path("/usr/bin/ffmpeg").exists() and not __import__("shutil").which("ffmpeg"),
        reason="ffmpeg ausente",
    )
    def test_mp3_128k_roundtrip(self):
        t = np.linspace(0, 1, 16000, endpoint=False, dtype=np.float32)
        audio = (0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
        out, sr, params = apply_augmentation(audio, 16000, "mp3_128k")
        assert len(out) > 0
        assert sr == 16000
        assert params["bitrate_kbps"] == 128

    @pytest.mark.skipif(
        not Path("/usr/bin/ffmpeg").exists() and not __import__("shutil").which("ffmpeg"),
        reason="ffmpeg ausente",
    )
    def test_opus_32k_roundtrip(self):
        t = np.linspace(0, 1, 16000, endpoint=False, dtype=np.float32)
        audio = (0.3 * np.sin(2 * np.pi * 880 * t)).astype(np.float32)
        out, sr, params = apply_augmentation(audio, 16000, "opus_32k")
        assert len(out) > 0
        assert sr == 16000
        assert params["bitrate_kbps"] == 32


class TestAudioLrStratifiedSampling:
    def test_sample_stratified_balances_augmentations(self):
        rows = []
        for aug in ["", "mp3_128k", "opus_32k", "noise_snr_20", "noise_snr_15"]:
            for i in range(20):
                rows.append({"augmentation": aug, "y_fake": i % 2, "dataset": "X", "generator": "G"})
        df = pd.DataFrame(rows)
        rng = np.random.default_rng(20260704)
        sampled = _sample_stratified(df, n_total=10, rng=rng, context="test")
        assert len(sampled) == 10
        counts = sampled["augmentation"].value_counts()
        assert set(counts.index) == set(AUGMENTATION_NAMES) | {""}
        assert counts.min() == 2
        assert counts.max() == 2
