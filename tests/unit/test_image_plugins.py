"""Tests for image forensic plugins — TDD Red phase.

Expected: ALL tests fail because image plugins do not exist yet.
"""

import os
import tempfile

import numpy as np
import pytest
from PIL import Image


@pytest.fixture
def sample_jpg():
    """Create a temporary JPEG image for testing."""
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        img = Image.new("RGB", (100, 100), color="red")
        img.save(f.name, "JPEG", quality=95)
        yield f.name
    os.unlink(f.name)


@pytest.fixture
def sample_png():
    """Create a temporary PNG image with noise pattern for testing."""
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        arr = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
        img = Image.fromarray(arr)
        img.save(f.name, "PNG")
        yield f.name
    os.unlink(f.name)


class TestELAPlugin:
    """TU-IMG-001 to TU-IMG-003"""

    def test_ela_analyzes_jpeg(self, sample_jpg):
        """TU-IMG-001: ELA plugin analyzes JPEG and returns heatmap path."""
        from core.plugins.ela_plugin import ELAPlugin
        plugin = ELAPlugin()
        result = plugin.analyze(sample_jpg, {"quality": 95})

        assert result["success"] is True
        assert "heatmap_path" in result
        assert "ela_score" in result
        assert os.path.exists(result["heatmap_path"])

    def test_ela_accepts_png(self, sample_png):
        """TU-IMG-002: ELA plugin accepts PNG and converts internally to JPEG for analysis."""
        from core.plugins.ela_plugin import ELAPlugin
        plugin = ELAPlugin()
        result = plugin.analyze(sample_png, {"quality": 95})

        assert result["success"] is True
        assert "heatmap_path" in result
        assert os.path.exists(result["heatmap_path"])

    def test_ela_writes_heatmap_base_at_unit_gain(self, sample_jpg):
        from core.plugins.ela_plugin import ELAPlugin

        plugin = ELAPlugin()
        result = plugin.analyze(sample_jpg, {"quality": 95, "gain": 3.0})

        assert result["success"] is True
        assert os.path.exists(result["heatmap_base_path"])
        assert os.path.exists(result["heatmap_path"])

    def test_ela_validate_parameters(self):
        """TU-IMG-003: ELA validates quality parameter."""
        from core.plugins.ela_plugin import ELAPlugin
        plugin = ELAPlugin()

        valid, _ = plugin.validate_parameters({"quality": 90})
        assert valid is True

        valid, msg = plugin.validate_parameters({"quality": 10})
        assert valid is False
        assert "quality" in msg.lower()

    def test_ela_channel_mode_y(self, sample_jpg):
        from core.plugins.ela_plugin import ELAPlugin

        plugin = ELAPlugin()
        result = plugin.analyze(sample_jpg, {"quality": 95, "channel_mode": "y"})
        assert result["success"] is True
        assert result["channel_mode"] == "y"

    def test_ela_channel_mode_crominancia(self, sample_jpg):
        from core.plugins.ela_plugin import ELAPlugin

        plugin = ELAPlugin()
        result = plugin.analyze(sample_jpg, {"quality": 95, "channel_mode": "crominancia"})
        assert result["success"] is True
        assert result["channel_mode"] == "crominancia"

    def test_ela_invalid_channel_mode(self):
        from core.plugins.ela_plugin import ELAPlugin

        plugin = ELAPlugin()
        valid, msg = plugin.validate_parameters({"quality": 90, "channel_mode": "invalid"})
        assert valid is False
        assert "channel_mode" in msg


class TestMetadataPlugin:
    """TU-IMG-004 to TU-IMG-006"""

    def test_metadata_extracts_exif(self, sample_jpg):
        """TU-IMG-004: Metadata plugin extracts EXIF from JPEG."""
        from core.plugins.metadata_plugin import MetadataPlugin
        plugin = MetadataPlugin()
        result = plugin.analyze(sample_jpg, {})

        assert result["success"] is True
        assert "summary" in result
        assert "file" in result
        assert result["file"]["format"] == "JPEG"
        assert "metadata" in result
        assert "families" in result["metadata"]
        assert "jpeg_structure" in result
        assert result["jpeg_structure"]["available"] is True
        assert len(result["jpeg_structure"]["quantization_tables"]) >= 1

    def test_metadata_supports_multiple_formats(self, sample_png):
        """TU-IMG-005: Metadata plugin works with PNG too."""
        from core.plugins.metadata_plugin import MetadataPlugin
        plugin = MetadataPlugin()
        result = plugin.analyze(sample_png, {})

        assert result["success"] is True
        assert result["file"]["format"] == "PNG"

    def test_metadata_no_required_params(self):
        """TU-IMG-006: Metadata plugin accepts any parameters."""
        from core.plugins.metadata_plugin import MetadataPlugin
        plugin = MetadataPlugin()
        valid, _ = plugin.validate_parameters({"anything": 123})
        assert valid is True

