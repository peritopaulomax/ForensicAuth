"""Testes da sequência de marcadores JPEG."""

import os
import tempfile

import pytest
from PIL import Image

from core.metadata.jpeg_markers import _collapse_rst_markers, scan_jpeg_marker_sequence
from core.metadata.jpeg_structure import read_jpeg_structure


@pytest.fixture
def sample_jpg():
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        Image.new("RGB", (64, 64), color="red").save(f.name, "JPEG", quality=85)
        yield f.name
    os.unlink(f.name)


class TestJpegMarkers:
    def test_scan_starts_with_soi(self, sample_jpg):
        result = scan_jpeg_marker_sequence(sample_jpg)
        assert result["available"] is True
        markers = result["markers"]
        assert markers[0]["name"] == "SOI"
        assert markers[0]["code_hex"] == "FFD8"

    def test_scan_contains_dqt_sof_sos_eoi(self, sample_jpg):
        result = scan_jpeg_marker_sequence(sample_jpg)
        names = [m["name"] for m in result["markers"]]
        assert "DQT" in names
        assert any(n.startswith("SOF") for n in names)
        assert "SOS" in names
        assert "EOI" in names
        assert names[-1] == "EOI"

    def test_scan_has_summary_string(self, sample_jpg):
        result = scan_jpeg_marker_sequence(sample_jpg)
        assert "SOI" in result["summary"]
        assert "EOI" in result["summary"]

    def test_read_jpeg_structure_includes_marker_sequence(self, sample_jpg):
        struct = read_jpeg_structure(sample_jpg)
        assert struct["marker_scan_available"] is True
        assert struct["marker_count"] >= 5
        assert struct["marker_sequence"]
        assert "SOI" in struct["marker_summary"]

    def test_collapse_rst_markers_into_single_entry(self):
        raw = [
            {"index": 0, "offset": 0, "code_hex": "FFD8", "name": "SOI", "segment_length": 2},
            {"index": 1, "offset": 100, "code_hex": "FFD0", "name": "RST0", "segment_length": None},
            {"index": 2, "offset": 200, "code_hex": "FFD1", "name": "RST1", "segment_length": None},
            {"index": 3, "offset": 300, "code_hex": "FFD2", "name": "RST2", "segment_length": None},
            {"index": 4, "offset": 400, "code_hex": "FFD9", "name": "EOI", "segment_length": 2},
        ]
        collapsed = _collapse_rst_markers(raw)
        names = [m["name"] for m in collapsed]
        assert names == ["SOI", "RST(3)", "EOI"]
        rst = collapsed[1]
        assert rst["rst_count"] == 3
        assert rst["offset"] == 100
