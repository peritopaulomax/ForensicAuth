"""Testes de exportação da grade posicional JPEG."""

import json
import os
import tempfile

import pytest
from PIL import Image

from core.metadata.jpeg_structure_compare import build_positional_grid_report, build_similarity_matrix
from core.metadata.jpeg_structure_grid_export import (
    enrich_grid_payload,
    render_grid_txt,
)


@pytest.fixture
def sample_jpg():
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        Image.new("RGB", (64, 64), color="red").save(f.name, "JPEG", quality=85)
        yield f.name
    os.unlink(f.name)


@pytest.fixture
def sample_jpg_alt():
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        Image.new("RGB", (48, 48), color="blue").save(f.name, "JPEG", quality=70)
        yield f.name
    os.unlink(f.name)


@pytest.fixture
def grid_payload(sample_jpg, sample_jpg_alt):
    matrix = build_similarity_matrix(
        mode="with_reference",
        reference_paths=[sample_jpg],
        reference_labels=["ref.jpg"],
        reference_ids=["ref-id"],
        questioned_paths=[sample_jpg, sample_jpg_alt],
        questioned_labels=["q1.jpg", "q2.jpg"],
        questioned_ids=["q1", "q2"],
    )
    assert matrix["success"]
    grid = build_positional_grid_report(
        mode="with_reference",
        reference_structures=matrix["reference_structures"],
        questioned_structures=matrix["questioned_structures"],
    )
    assert grid["success"]
    return enrich_grid_payload(
        grid,
        reference_evidence_ids=["ref-id"],
        questioned_evidence_ids=["q1", "q2"],
    )


class TestJpegStructureGridExport:
    def test_grid_payload_has_comparisons(self, grid_payload):
        assert grid_payload["artifact_kind"] == "positional_grid"
        assert len(grid_payload["comparisons"]) >= 2
        assert grid_payload["reference_label"] == "ref.jpg"

    def test_render_grid_txt(self, grid_payload, tmp_path):
        txt = tmp_path / "grid.txt"
        render_grid_txt(grid_payload, txt)
        body = txt.read_text(encoding="utf-8")
        assert "grade posicional" in body.lower()
        assert "ref.jpg" in body

    def test_grid_json_roundtrip(self, grid_payload, tmp_path):
        path = tmp_path / "grid.json"
        path.write_text(json.dumps(grid_payload, ensure_ascii=False), encoding="utf-8")
        loaded = json.loads(path.read_text(encoding="utf-8"))
        assert loaded["reference_evidence_id"] == "ref-id"
