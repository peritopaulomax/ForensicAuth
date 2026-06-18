"""Integração: execução do plugin + formato aceito pelo frontend."""

import json
import os
import tempfile

import pytest
from PIL import Image

from core.metadata.jpeg_structure_compare import build_comparison_report
from core.plugins.jpeg_structure_compare_plugin import JpegStructureComparePlugin


@pytest.fixture
def two_jpegs():
    paths = []
    for color in ("red", "blue"):
        f = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        Image.new("RGB", (32, 32), color=color).save(f.name, "JPEG", quality=85)
        paths.append(f.name)
    yield paths
    for p in paths:
        os.unlink(p)


class TestJpegStructureCompareIntegration:
    def test_plugin_analyze_matches_report_shape(self, two_jpegs):
        plugin = JpegStructureComparePlugin()
        params = {
            "evidence_ids": ["a", "b"],
            "evidence_paths": two_jpegs,
            "evidence_labels": ["a.jpg", "b.jpg"],
            "reference_index": 0,
        }
        ok, msg = plugin.validate_parameters(params)
        assert ok, msg

        result = plugin.analyze(two_jpegs[0], params)
        assert result["success"] is True
        assert result["comparisons"]
        assert result["structures"]
        assert "reference_marker" not in result["comparisons"][0]["cells"][0]

        # Payload serializável e compacto o suficiente para UI
        blob = json.dumps(result)
        assert len(blob) < 200_000

    def test_report_dqt_diff_detected(self, two_jpegs):
        report = build_comparison_report(
            two_jpegs,
            ["ref.jpg", "alt.jpg"],
            ["id1", "id2"],
        )
        assert report["success"] is True
        dqt_markers = [
            m for m in report["structures"][0]["comparison_markers"] if m.get("name") == "DQT"
        ]
        assert len(dqt_markers) >= 1
        assert all(m.get("dqt_tables") for m in dqt_markers)

    def test_plugin_matrix_all_pairs(self, two_jpegs):
        plugin = JpegStructureComparePlugin()
        params = {
            "mode": "all_pairs",
            "questioned_evidence_ids": ["a", "b"],
            "questioned_paths": two_jpegs,
            "questioned_labels": ["a.jpg", "b.jpg"],
        }
        ok, msg = plugin.validate_parameters(params)
        assert ok, msg
        result = plugin.analyze(two_jpegs[0], params)
        assert result["success"] is True
        assert result["mode"] == "all_pairs"
        assert result["matrix"]["rows"]
