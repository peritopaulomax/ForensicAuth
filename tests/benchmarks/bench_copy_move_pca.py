"""Performance benchmark for Copy-Move PCA pipeline."""

from __future__ import annotations

import os
import time
from pathlib import Path

import cv2
import numpy as np
import pytest

WORKSPACE = Path(__file__).resolve().parents[2]


def _synthetic_copymove(h: int, w: int) -> np.ndarray:
    rng = np.random.default_rng(0)
    img = rng.integers(40, 200, (h, w), dtype=np.uint8)
    ph, pw = min(100, h // 3), min(100, w // 3)
    patch = img[50 : 50 + ph, 20 : 20 + pw].copy()
    img[10 : 10 + ph, w - pw - 20 : w - 20] = patch
    return img


@pytest.mark.benchmark
class TestCopyMovePcaBenchmark:
    def test_512_full(self, benchmark):
        from core.legacy.copy_move_pca import run_copy_move_pca

        gray = _synthetic_copymove(512, 512)
        result = benchmark.pedantic(
            run_copy_move_pca,
            args=(gray, {"max_side": 0, "nf": 128}),
            iterations=1,
            rounds=1,
        )
        assert result["mask"].sum() >= 0

    @pytest.mark.slow
    def test_1080p_timing_gate(self):
        from core.legacy.copy_move_pca import run_copy_move_pca

        gray = _synthetic_copymove(1080, 1920)
        os.environ.setdefault("NUMBA_NUM_THREADS", "4")
        t0 = time.perf_counter()
        run_copy_move_pca(gray, {"max_side": 0, "nf": 128})
        elapsed = time.perf_counter() - t0
        assert elapsed <= 120.0, f"1080p took {elapsed:.1f}s (gate 120s)"

    def test_roi_800x600_timing_gate(self):
        from core.legacy.copy_move_pca import run_copy_move_pca

        gray = _synthetic_copymove(1080, 1920)
        t0 = time.perf_counter()
        run_copy_move_pca(
            gray,
            {"max_side": 0, "nf": 128, "region": [560, 240, 800, 600]},
        )
        elapsed = time.perf_counter() - t0
        assert elapsed <= 30.0, f"ROI 800x600 took {elapsed:.1f}s (gate 30s)"
