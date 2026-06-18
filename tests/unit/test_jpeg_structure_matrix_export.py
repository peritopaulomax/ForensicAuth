"""Testes de exportação de matriz JPEG (JSON/PNG/TXT)."""

import json
import os
import tempfile
from pathlib import Path

import pytest
from PIL import Image

from core.metadata.jpeg_structure_matrix_export import (
    COMPARISON_CRITERIA_VERSION,
    enrich_matrix_payload,
    render_matrix_png,
    render_matrix_txt,
)
from core.metadata.jpeg_structure_compare import build_similarity_matrix


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
def matrix_payload(sample_jpg, sample_jpg_alt, tmp_path):
    report = build_similarity_matrix(
        mode="with_reference",
        reference_paths=[sample_jpg],
        reference_labels=["ref.jpg"],
        reference_ids=["ref-id"],
        questioned_paths=[sample_jpg, sample_jpg_alt],
        questioned_labels=["q1.jpg", "q2.jpg"],
        questioned_ids=["q1", "q2"],
    )
    assert report["success"]
    return enrich_matrix_payload(
        report,
        reference_evidence_ids=["ref-id"],
        questioned_evidence_ids=["q1", "q2"],
    )


class TestJpegStructureMatrixExport:
    def test_enriched_json_has_audit_fields(self, matrix_payload):
        assert matrix_payload["technique"] == "jpeg_structure_compare"
        assert matrix_payload["criteria_version"] == COMPARISON_CRITERIA_VERSION
        assert matrix_payload["comparison_rules"]["dht"] == "position_only"
        assert matrix_payload["reference_evidence_ids"] == ["ref-id"]
        assert "R1" in matrix_payload["legend"]
        assert "Q1" in matrix_payload["legend"]

    def test_render_png_and_txt(self, matrix_payload, tmp_path):
        png = tmp_path / "matrix.png"
        txt = tmp_path / "report.txt"
        render_matrix_png(matrix_payload, png)
        render_matrix_txt(matrix_payload, txt)
        assert png.exists() and png.stat().st_size > 100
        body = txt.read_text(encoding="utf-8")
        assert "Comparação de estruturas JPEG" in body
        assert "R1 × Q1" in body or "Coincidências" in body

    def test_json_roundtrip(self, matrix_payload, tmp_path):
        path = tmp_path / "out.json"
        path.write_text(json.dumps(matrix_payload, ensure_ascii=False), encoding="utf-8")
        loaded = json.loads(path.read_text(encoding="utf-8"))
        assert loaded["legend"]["R1"] == "ref.jpg"
