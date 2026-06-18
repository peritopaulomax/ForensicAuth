"""Tests for legacy forensic plugins — DCT, JPEG Ghosts, Resampling, PRNU."""

import glob
import os
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest
from PIL import Image


@pytest.fixture
def sample_jpg():
    """Create a temporary JPEG image."""
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        img = Image.new("RGB", (256, 256), color="red")
        img.save(f.name, "JPEG", quality=85)
        yield f.name
    os.unlink(f.name)


class TestPRNULegacy:
    """TU-LEG-001: PRNU with real legacy code."""

    def test_prnu_fingerprint_exists(self):
        """Fingerprint file exists from previous generation."""
        assert os.path.exists("models/prnu/fingerprints/test_D70.npy")

    def test_prnu_authentic_high_pce(self):
        """Authentic image from same camera gives high PCE."""
        from core.plugins.prnu_adapter import PRNUAdapter
        adapter = PRNUAdapter()
        result = adapter.analyze(
            "Legados/imagens/02 - PRNU para Autenticidade e Fonte/padrao/Padrao D70/DSC_5270.JPG",
            {"fingerprint_path": "models/prnu/fingerprints/test_D70.npy", "mode": "full", "sigma": 2.0},
        )
        assert result["success"] is True
        assert result["pce"] > 1000  # High PCE for authentic
        assert "classification" not in result
        assert result.get("correlation_surface_html_path")
        assert os.path.exists(result["correlation_surface_html_path"])
        import json

        json.dumps(result)  # numpy int64 in peak_location must not break job result.json

    def test_prnu_different_lower_pce(self):
        """Different camera gives lower PCE."""
        from core.plugins.prnu_adapter import PRNUAdapter
        adapter = PRNUAdapter()
        result = adapter.analyze(
            "Legados/imagens/02 - PRNU para Autenticidade e Fonte/padrao/Padrao D70 Tipo 2/10.JPG",
            {"fingerprint_path": "models/prnu/fingerprints/test_D70.npy", "mode": "full", "sigma": 2.0},
        )
        assert result["success"] is True
        assert result["pce"] < 10000  # Lower than authentic


class TestDCTQuantization:
    """TU-LEG-002: DCT quantization estimation."""

    def test_dct_quantization_runs(self, sample_jpg):
        """DCT quantization plugin runs on JPEG."""
        from core.plugins.dct_quantization_plugin import DCTQuantizationPlugin
        plugin = DCTQuantizationPlugin()
        result = plugin.analyze(sample_jpg, {})
        assert result["success"] is True
        assert "quantization_matrix" in result
        qm = result["quantization_matrix"]
        assert len(qm) == 8
        assert len(qm[0]) == 8
        try:
            import jpegio  # noqa: F401

            assert "jpegio_matrix" in result
            jm = result["jpegio_matrix"]
            assert len(jm) == 8
            assert all(val > 0 for row in jm for val in row)
        except ImportError:
            pass


class TestZeroGrid:
    """TU-LEG-003b: ZERO grid (libzero.so_)."""

    def test_zero_unavailable_on_windows(self):
        from core.legacy.zero.libzero_loader import zero_runtime_status

        if sys.platform != "win32":
            pytest.skip("Windows-only probe")
        ok, reason = zero_runtime_status()
        assert ok is False
        assert "Windows" in reason or "Linux" in reason

    @pytest.mark.skipif(sys.platform == "win32", reason="libzero.so_ requires Linux")
    def test_zero_grid_runs(self, sample_jpg):
        from core.plugins.zero_grid_plugin import ZeroGridPlugin

        ok, _ = ZeroGridPlugin.is_runtime_available()
        if not ok:
            pytest.skip("libzero not available")

        plugin = ZeroGridPlugin()
        result = plugin.analyze(sample_jpg, {"include_simulation": False})
        assert result["success"] is True
        assert "votes_colored_image_path" in result
        assert Path(result["votes_colored_image_path"]).exists()


class TestJPEGGhosts:
    """TU-LEG-003: JPEG Ghosts detection."""

    def test_jpeg_ghosts_runs(self, sample_jpg, monkeypatch):
        """JPEG Ghosts plugin runs (legacy Farid pipeline)."""
        monkeypatch.setenv("JPEG_GHOSTS_N_JOBS", "1")
        from app.config import get_settings

        get_settings.cache_clear()
        from core.plugins.jpeg_ghosts_plugin import JPEGGhostsPlugin
        plugin = JPEGGhostsPlugin()
        result = plugin.analyze(
            sample_jpg,
            {
                "qmin": 50,
                "qmax": 70,
                "step": 10,
                "shift_search": False,
            },
        )
        get_settings.cache_clear()
        assert result["success"] is True
        assert result["best_quality"] is not None
        assert "ghost_map_image_path" in result
        assert Path(result["ghost_map_image_path"]).exists()
        assert "metric_peaks_by_quality" in result


class TestResampling:
    """TU-LEG-004: Resampling detection."""

    def test_resampling_runs(self, sample_jpg):
        """Resampling plugin runs without error."""
        from core.plugins.resampling_plugin import ResamplingPlugin
        plugin = ResamplingPlugin()
        result = plugin.analyze(sample_jpg, {})
        assert result["success"] is True
        assert "peak_value_vertical" in result
        assert "spectrum_v_image_path" in result


class TestDoubleCompression:
    """TU-LEG-005: Double JPEG compression."""

    def test_double_compression_runs(self, sample_jpg):
        from core.plugins.double_compression_plugin import DoubleCompressionPlugin
        plugin = DoubleCompressionPlugin()
        result = plugin.analyze(sample_jpg, {"dctmin": 1, "dctmax": 3})
        if result["success"]:
            assert "interactive_html_path" in result
            assert Path(result["interactive_html_path"]).exists()
            assert result["coefficient_count"] == 3
        else:
            assert "jpegio" in result.get("error", "").lower() or "jpeg" in result.get("error", "").lower()


class TestBagExtraction:
    """TU-LEG-006: BAG block grid extraction."""

    def test_bag_extraction_runs(self, sample_jpg):
        from core.plugins.bag_extraction_plugin import BagExtractionPlugin
        plugin = BagExtractionPlugin()
        result = plugin.analyze(sample_jpg, {})
        assert result["success"] is True
        assert "bag_map_image_path" in result


class TestPatchMatch:
    """TU-LEG-007: PatchMatch copy-move (slow — small image)."""

    @pytest.mark.slow
    def test_patchmatch_runs(self, sample_jpg):
        from core.plugins.patchmatch_plugin import PatchMatchPlugin
        plugin = PatchMatchPlugin()
        result = plugin.analyze(
            sample_jpg,
            {"p": 8, "min_dn": 32, "iterations": 2, "min_region_size": 64},
        )
        assert result["success"] is True
        assert "mask_image_path" in result
        assert "vectors_image_path" in result
        assert "colored_overlay_image_path" in result


class TestCopyMovePca:
    """TU-LEG-008: Copy-Move PCA (slow — small image)."""

    @pytest.mark.slow
    def test_copy_move_pca_runs(self, sample_jpg):
        from core.plugins.copy_move_pca_plugin import CopyMovePcaPlugin
        plugin = CopyMovePcaPlugin()
        result = plugin.analyze(
            sample_jpg,
            {"nf": 96, "max_side": 512, "morph": False},
        )
        assert result["success"] is True
        assert "mask_image_path" in result
        assert "overlay_image_path" in result
        assert "colored_overlay_image_path" in result
