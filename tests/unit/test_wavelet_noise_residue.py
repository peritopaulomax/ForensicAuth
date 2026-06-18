"""Tests for Wavelets Noise Residue (Peritus INC / Mahdian & Saic 2009)."""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

WORKSPACE = Path(__file__).resolve().parents[2]
PERITUS_DWT = WORKSPACE / "Legados" / "Peritus" / "waveletnoiseresidue" / "dwt.c"
REF_BIN = WORKSPACE / "tools" / "wavelet_noise_residue_ref"
GOLDEN = WORKSPACE / "tests" / "fixtures" / "images" / "wavelet_noise_residue_golden.png"
EXEMPLO3_26JPG = WORKSPACE / "uploads-dev" / "73508d40-a644-4429-8c81-73c348ae98d5.jpg"


def _synthetic_gray(h: int = 256, w: int = 256) -> np.ndarray:
    rng = np.random.default_rng(11)
    img = rng.integers(30, 220, (h, w), dtype=np.uint8)
    ph, pw = min(h // 4, 80), min(w // 4, 80)
    if ph > 8 and pw > 8 and 10 + ph <= h and 10 + pw <= w and h - ph - 10 >= 0:
        patch = img[10 : 10 + ph, 10 : 10 + pw].copy()
        img[h - ph - 10 : h - 10, w - pw - 10 : w - 10] = patch
    return img


@pytest.fixture
def sample_gray() -> np.ndarray:
    return _synthetic_gray(256, 256)


class TestWaveletDwt:
    def test_scaling_orders(self):
        from core.legacy.wavelet_noise_residue.dwt import scaling_coefficients

        for order in (2, 4, 6, 8, 10):
            h = scaling_coefficients(order)
            assert h.shape[0] == order

    def test_dwt_produces_finite_output(self, sample_gray):
        from core.legacy.wavelet_noise_residue.dwt import dwt_x, scaling_coefficients

        x = sample_gray.astype(np.float64)
        y = dwt_x(x, scaling_coefficients(8), 1)
        assert y.shape == x.shape
        assert np.isfinite(y).all()


class TestWaveletNoiseResiduePipeline:
    def test_smoke_defaults(self, sample_gray):
        from core.legacy.wavelet_noise_residue import run_wavelet_noise_residue

        result = run_wavelet_noise_residue(sample_gray)
        assert result["colored_bgr"].shape[:2] == sample_gray.shape
        assert result["overlay_bgr"].shape == result["colored_bgr"].shape

    def test_deterministic(self, sample_gray):
        from core.legacy.wavelet_noise_residue import run_wavelet_noise_residue

        params = {"order": 8, "blocksize": 40, "thr": 255, "post": True}
        r1 = run_wavelet_noise_residue(sample_gray, params)
        r2 = run_wavelet_noise_residue(sample_gray, params)
        h1 = hashlib.sha256(r1["colored_bgr"].tobytes()).hexdigest()
        h2 = hashlib.sha256(r2["colored_bgr"].tobytes()).hexdigest()
        assert h1 == h2

    def test_peritus_default_params(self, sample_gray):
        from core.legacy.wavelet_noise_residue import run_wavelet_noise_residue

        result = run_wavelet_noise_residue(
            sample_gray,
            {"levels_slider": 4, "blocksize": 40, "thr": 255, "post": True},
        )
        assert result["parameters"]["order"] == 8

    def test_roi(self, sample_gray):
        from core.legacy.wavelet_noise_residue import run_wavelet_noise_residue

        full = run_wavelet_noise_residue(sample_gray)
        roi = run_wavelet_noise_residue(sample_gray, {"region": [64, 64, 128, 128]})
        assert roi["colored_bgr"].shape == full["colored_bgr"].shape
        assert roi["prep_meta"]["roi_applied"] is True

    @pytest.mark.skipif(not EXEMPLO3_26JPG.is_file(), reason="26.jpg do caso Exemplo3 ausente")
    def test_exemplo3_26jpg_odd_dimensions(self):
        """Regressao: 26.jpg (343x585) falhava com index out of bounds no DWT."""
        from core.legacy.wavelet_noise_residue import run_wavelet_noise_residue

        gray = cv2.imread(str(EXEMPLO3_26JPG), cv2.IMREAD_GRAYSCALE)
        assert gray is not None
        assert gray.shape == (343, 585)

        result = run_wavelet_noise_residue(gray)
        assert result["colored_bgr"].shape[:2] == gray.shape
        assert result["overlay_bgr"].shape == result["colored_bgr"].shape

    def test_odd_dimension_dwt_convolution(self):
        from core.legacy.wavelet_noise_residue.dwt import dwt_coefficients, dwt_convolution, scaling_coefficients

        coeff_low, coeff_high = dwt_coefficients(scaling_coefficients(8))
        x_in = np.arange(585, dtype=np.float64)
        low, high = dwt_convolution(x_in, 585, coeff_low, coeff_high)
        assert low.shape[0] == (585 + 1) // 2
        assert high.shape == low.shape

    def test_reprocess_from_npz_without_redwt(self, sample_gray, tmp_path):
        from core.legacy.wavelet_noise_residue import (
            reprocess_wavelet_noise_residue_from_npz,
            run_wavelet_noise_residue,
        )

        npz_path = tmp_path / "wnr_dwt_coefficients.npz"
        params = {"order": 8, "blocksize": 7, "thr": 128, "post": True}
        full = run_wavelet_noise_residue(sample_gray, params, dwt_coefficients_path=npz_path)
        assert npz_path.is_file()
        assert (tmp_path / "wnr_agg_bs7.npy").is_file()

        replay = reprocess_wavelet_noise_residue_from_npz(npz_path, blocksize=7, thr=128, post=True)
        assert np.array_equal(full["colored_bgr"], replay["colored_bgr"])

        other = reprocess_wavelet_noise_residue_from_npz(npz_path, blocksize=3, thr=255, post=True)
        assert other["colored_bgr"].shape == full["colored_bgr"].shape
        assert not np.array_equal(other["colored_bgr"], full["colored_bgr"])

    def test_threshold_preview_uses_aggregate_cache(self, sample_gray, tmp_path):
        import time
        from core.legacy.wavelet_noise_residue import reprocess_wavelet_noise_residue_from_npz, run_wavelet_noise_residue

        npz_path = tmp_path / "wnr_dwt_coefficients.npz"
        run_wavelet_noise_residue(sample_gray, {"order": 8, "blocksize": 3}, dwt_coefficients_path=npz_path)
        cache = tmp_path / "wnr_agg_bs3.npy"
        assert cache.is_file()

        t0 = time.perf_counter()
        reprocess_wavelet_noise_residue_from_npz(npz_path, blocksize=3, thr=64, post=True)
        cached_elapsed = time.perf_counter() - t0
        assert cached_elapsed < 1.0

    @pytest.mark.slow
    def test_golden_regression(self, sample_gray):
        from core.legacy.wavelet_noise_residue import wavelets_noise_residue

        out = wavelets_noise_residue(sample_gray, order=8, blocksize=40, thr=255, post=True)
        if not GOLDEN.is_file():
            cv2.imwrite(str(GOLDEN), out)
            pytest.skip("Golden criado — reexecute para validar")

        golden = cv2.imread(str(GOLDEN))
        assert golden is not None
        assert golden.shape == out.shape
        agree = float(np.mean(golden == out))
        assert agree >= 0.99, f"Acordo pixel {agree:.4f} abaixo de 0.99"


class TestWaveletNoiseResiduePlugin:
    def test_plugin_registered(self):
        from core.plugin_registry import PluginRegistry

        plugins_dir = WORKSPACE / "src" / "backend" / "core" / "plugins"
        registry = PluginRegistry()
        registry.discover_and_register(str(plugins_dir))
        assert registry.get("wavelet_noise_residue") is not None

    def test_validate_parameters(self):
        from core.plugins.wavelet_noise_residue_plugin import WaveletNoiseResiduePlugin

        plugin = WaveletNoiseResiduePlugin()
        ok, _ = plugin.validate_parameters({"order": 8, "blocksize": 40})
        assert ok
        ok, msg = plugin.validate_parameters({"order": 7})
        assert not ok


@pytest.mark.skipif(not PERITUS_DWT.is_file(), reason="Legado Peritus dwt.c ausente")
class TestPeritusCppEquivalence:
    """Compare Python port vs compilacao do dwt.c + logica filter.cpp."""

    @staticmethod
    def _ensure_ref_binary() -> Path:
        if REF_BIN.is_file():
            return REF_BIN
        src = WORKSPACE / "tools" / "wavelet_noise_residue_ref.c"
        if not src.is_file():
            pytest.skip("tools/wavelet_noise_residue_ref.c ausente")
        try:
            subprocess.run(
                [
                    "g++",
                    "-O3",
                    "-o",
                    str(REF_BIN),
                    str(src),
                    str(PERITUS_DWT),
                    f"-I{PERITUS_DWT.parent}",
                    "-lopencv_core",
                    "-lopencv_imgproc",
                    "-lopencv_imgcodecs",
                ],
                check=True,
                capture_output=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            pytest.skip(f"Referencia C++ Peritus indisponivel (opencv dev / g++): {exc}")
        return REF_BIN

    def test_cpp_reference_matches_python(self, sample_gray):
        from core.legacy.wavelet_noise_residue import wavelets_noise_residue

        ref = self._ensure_ref_binary()
        h, w = sample_gray.shape
        raw_in = WORKSPACE / "tests" / "fixtures" / "tmp_wnr_in.raw"
        raw_out = WORKSPACE / "tests" / "fixtures" / "tmp_wnr_out.raw"
        raw_in.parent.mkdir(parents=True, exist_ok=True)
        sample_gray.astype(np.uint8).tofile(raw_in)

        subprocess.run(
            [str(ref), str(raw_in), str(w), str(h), str(raw_out), "8", "40", "255", "1"],
            check=True,
            capture_output=True,
        )
        cpp_bgr = np.fromfile(raw_out, dtype=np.uint8).reshape(h, w, 3)
        py_bgr = wavelets_noise_residue(sample_gray, order=8, blocksize=40, thr=255, post=True)

        agree = float(np.mean(cpp_bgr == py_bgr))
        assert agree >= 0.98, f"Equivalencia Peritus C++ vs Python: {agree:.2%}"


class TestWaveletNoiseResiduePluginE2e:
    @pytest.mark.slow
    def test_plugin_runs(self, sample_gray, tmp_path):
        from core.plugins.wavelet_noise_residue_plugin import WaveletNoiseResiduePlugin

        path = tmp_path / "wnr_test.png"
        cv2.imwrite(str(path), sample_gray)
        plugin = WaveletNoiseResiduePlugin()
        ok, msg = plugin.validate_parameters({"order": 8, "blocksize": 40})
        assert ok, msg
        result = plugin.analyze(str(path), {"order": 8, "blocksize": 40, "thr": 255, "post": True})
        assert result["success"] is True
        assert Path(result["overlay_image_path"]).is_file()


class TestPrnuDenoisingDistinct:
    """PRNU usa Wiener db4 L=4; Peritus WNR usa DWT db8 L=1 + mediana HH — algoritmos distintos."""

    def test_not_same_as_prnu_noise_extract(self, sample_gray):
        from core.legacy.prnu.Filter import NoiseExtractFromImage
        from core.legacy.wavelet_noise_residue import wavelets_noise_residue

        gray3 = cv2.cvtColor(sample_gray, cv2.COLOR_GRAY2BGR)
        prnu = NoiseExtractFromImage(gray3, sigma=2.0)
        wnr = wavelets_noise_residue(sample_gray)
        wnr_gray = cv2.cvtColor(wnr, cv2.COLOR_BGR2GRAY)
        corr = np.corrcoef(prnu.ravel().astype(np.float64), wnr_gray.ravel().astype(np.float64))[0, 1]
        assert abs(corr) < 0.95, "WNR Peritus nao deve ser identico ao residuo PRNU"
