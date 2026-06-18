"""Tests for Copy-Move PCA (Popescu & Farid / Peritus port)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import cv2
import numpy as np
import pytest

WORKSPACE = Path(__file__).resolve().parents[2]
FIXTURE = WORKSPACE / "tests" / "fixtures" / "images" / "copymove.jpg"
GOLDEN = WORKSPACE / "tests" / "fixtures" / "images" / "copymove_pca_golden_mask.png"
EXEMPLO3_26JPG = WORKSPACE / "uploads-dev" / "73508d40-a644-4429-8c81-73c348ae98d5.jpg"
PERITUS_26_SCREENSHOT = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "images"
    / "exemplo3_26_peritus_reference.png"
)


def _make_copymove_array(size: int = 256) -> np.ndarray:
    rng = np.random.default_rng(7)
    img = rng.integers(40, 200, (size, size), dtype=np.uint8)
    patch = img[50:150, 20:120].copy()
    img[10:110, 140:240] = patch
    return img


@pytest.fixture
def sample_copymove_path(tmp_path) -> Path:
    if FIXTURE.is_file():
        return FIXTURE
    path = tmp_path / "copymove.jpg"
    cv2.imwrite(str(path), _make_copymove_array())
    return path


class TestCopyMovePcaPipeline:
    def test_smoke_defaults(self, sample_copymove_path):
        from core.legacy.copy_move_pca import run_copy_move_pca

        gray = cv2.imread(str(sample_copymove_path), cv2.IMREAD_GRAYSCALE)
        result = run_copy_move_pca(gray)
        assert result["mask"].shape == gray.shape
        assert result["colored_bgr"].shape[:2] == gray.shape[:2]
        assert result["clone_regions_detected"] >= 0

    def test_detects_synthetic_copymove(self, sample_copymove_path):
        from core.legacy.copy_move_pca import run_copy_move_pca

        gray = cv2.imread(str(sample_copymove_path), cv2.IMREAD_GRAYSCALE)
        result = run_copy_move_pca(gray, {"nf": 64, "nd": 8})
        assert int(np.count_nonzero(result["mask"])) > 0

    def test_deterministic_mask(self, sample_copymove_path):
        from core.legacy.copy_move_pca import run_copy_move_pca

        gray = cv2.imread(str(sample_copymove_path), cv2.IMREAD_GRAYSCALE)
        params = {"nf": 96, "morph": False, "max_side": 512}
        r1 = run_copy_move_pca(gray, params)
        r2 = run_copy_move_pca(gray, params)
        h1 = hashlib.sha256(r1["mask"].tobytes()).hexdigest()
        h2 = hashlib.sha256(r2["mask"].tobytes()).hexdigest()
        assert h1 == h2

    def test_roi_reduces_blocks(self):
        from core.legacy.copy_move_pca import run_copy_move_pca

        gray = _make_copymove_array(320)
        full = run_copy_move_pca(gray, {"max_side": 0, "nf": 128})
        roi = run_copy_move_pca(
            gray,
            {"max_side": 0, "nf": 128, "region": [100, 100, 120, 120]},
        )
        assert roi["nb_blocks"] < full["nb_blocks"]

    @pytest.mark.slow
    def test_golden_mask_regression(self, sample_copymove_path):
        from core.legacy.copy_move_pca import run_copy_move_pca

        gray = cv2.imread(str(sample_copymove_path), cv2.IMREAD_GRAYSCALE)
        params = {"nf": 96, "morph": False, "max_side": 512}
        result = run_copy_move_pca(gray, params)
        mask = result["mask"]

        if not GOLDEN.is_file():
            cv2.imwrite(str(GOLDEN), mask)
            pytest.skip("Golden mask created — re-run to validate regression")

        golden = cv2.imread(str(GOLDEN), cv2.IMREAD_GRAYSCALE)
        assert golden is not None
        assert golden.shape == mask.shape
        # Structural similarity proxy: fraction of matching non-zero pattern
        agree = np.mean((mask > 0) == (golden > 0))
        assert agree >= 0.85, f"Mask agreement {agree:.3f} below threshold"


class TestExemplo3CopyMoveRegression:
    @pytest.mark.skipif(not EXEMPLO3_26JPG.is_file(), reason="26.jpg do caso Exemplo3 ausente")
    def test_exemplo3_26jpg_matches_peritus_structure(self):
        """Regressao Exemplo3/26.jpg — 4 pares clonados como no Peritus Desktop."""
        from core.legacy.copy_move_pca import run_copy_move_pca

        gray = cv2.imread(str(EXEMPLO3_26JPG), cv2.IMREAD_GRAYSCALE)
        assert gray is not None
        result = run_copy_move_pca(gray)
        colored = result["colored_bgr"]
        out_bin = np.max(colored, axis=2) > 0

        assert result["clone_regions_detected"] == 4, (
            f"Esperado 4 pares unicos, obteve {result['clone_regions_detected']}"
        )
        mask_ratio = float(np.count_nonzero(out_bin) / gray.size)
        assert 0.01 < mask_ratio < 0.06, f"Mascara cobre {mask_ratio:.1%} da imagem"

        if PERITUS_26_SCREENSHOT.is_file():
            peritus = cv2.imread(str(PERITUS_26_SCREENSHOT))
            h, w = gray.shape
            peritus = cv2.resize(peritus, (w, h), interpolation=cv2.INTER_NEAREST)
            ref_bin = np.max(peritus, axis=2) > 10
            iou = float((ref_bin & out_bin).sum() / max(1, (ref_bin | out_bin).sum()))
            assert iou >= 0.75, f"IoU vs screenshot Peritus {iou:.3f} abaixo de 0.75"


class TestCopyMovePcaPlugin:
    @pytest.mark.slow
    def test_plugin_runs(self, sample_copymove_path):
        from core.plugins.copy_move_pca_plugin import CopyMovePcaPlugin

        plugin = CopyMovePcaPlugin()
        ok, msg = plugin.validate_parameters({"b": 7, "n_comp": 0.75})
        assert ok, msg
        result = plugin.analyze(
            str(sample_copymove_path),
            {"nf": 96, "max_side": 512, "morph": False},
        )
        assert result["success"] is True
        assert Path(result["mask_image_path"]).is_file()
        assert Path(result["overlay_image_path"]).is_file()
