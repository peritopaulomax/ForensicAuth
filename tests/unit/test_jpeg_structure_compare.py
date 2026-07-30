"""JPEG structure: dump, compare, markers, grid/matrix export.\n\nMERGE mecânico (Fase 3d) — anexados markers/grid/matrix export.\nMantido separado: test_jpeg_structure_compare_integration.py\n"""

import json
import os
import tempfile
from pathlib import Path

import pytest
from PIL import Image

from core.metadata.jpeg_markers import _collapse_rst_markers, scan_jpeg_marker_sequence
from core.metadata.jpeg_structure import read_jpeg_structure
from core.metadata.jpeg_structure_compare import (
    build_comparison_report,
    build_positional_grid_report,
    build_similarity_matrix,
    compare_jpeg_structures,
)
from core.metadata.jpeg_structure_dump import (
    dump_jpeg_structure,
    is_jpeg_file,
    parse_dht_payload,
    parse_dqt_payload,
)
from core.metadata.jpeg_structure_grid_export import enrich_grid_payload, render_grid_txt
from core.metadata.jpeg_structure_matrix_export import (
    COMPARISON_CRITERIA_VERSION,
    enrich_matrix_payload,
    render_matrix_png,
    render_matrix_txt,
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


class TestJpegStructureDump:
    def test_is_jpeg_by_extension(self, sample_jpg):
        assert is_jpeg_file(sample_jpg) is True

    def test_dump_structure(self, sample_jpg):
        dump = dump_jpeg_structure(sample_jpg)
        assert dump["available"] is True
        names = [m["name"] for m in dump["comparison_markers"]]
        assert names[0] == "SOI"
        assert "DQT" in names
        assert "SOS" in names
        assert names[-1] == "EOI"

    def test_dqt_tables_parsed(self, sample_jpg):
        dump = dump_jpeg_structure(sample_jpg)
        dqt = next(m for m in dump["comparison_markers"] if m["name"] == "DQT")
        assert dqt.get("dqt_tables")
        assert len(dqt["dqt_tables"][0]["matrix"]) == 64

    def test_dht_tables_parsed(self, sample_jpg):
        dump = dump_jpeg_structure(sample_jpg)
        dht_markers = [m for m in dump["comparison_markers"] if m["name"] == "DHT"]
        assert dht_markers
        assert dht_markers[0].get("dht_tables")

    def test_parse_dqt_payload_roundtrip(self):
        payload = bytes([0]) + bytes(range(64))
        tables = parse_dqt_payload(payload)
        assert len(tables) == 1
        assert tables[0]["table_id"] == 0
        assert tables[0]["matrix"] == list(range(64))

    def test_parse_dht_payload_minimal(self):
        counts = [0, 1] + [0] * 14
        values = [5]
        payload = bytes([0x00]) + bytes(counts) + bytes(values)
        tables = parse_dht_payload(payload)
        assert len(tables) == 1
        assert tables[0]["table_class"] == 0
        assert tables[0]["values"] == [5]


class TestJpegStructureCompare:
    def test_identical_files_match(self, sample_jpg):
        dump_a = dump_jpeg_structure(sample_jpg)
        dump_b = dump_jpeg_structure(sample_jpg)
        result = compare_jpeg_structures(dump_a, dump_b)
        assert result["fully_matches"] is True
        assert all(c["status"] == "match" for c in result["cells"])

    def test_different_quality_diverges_on_dqt(self, sample_jpg, sample_jpg_alt):
        dump_a = dump_jpeg_structure(sample_jpg)
        dump_b = dump_jpeg_structure(sample_jpg_alt)
        result = compare_jpeg_structures(dump_a, dump_b)
        assert result["fully_matches"] is False
        dqt_cells = [c for c in result["cells"] if (c.get("reference_name") or c.get("candidate_name")) == "DQT"]
        assert any(c["status"] == "diverge" for c in dqt_cells)

    def test_build_comparison_report(self, sample_jpg, sample_jpg_alt):
        report = build_comparison_report(
            [sample_jpg, sample_jpg_alt],
            ["ref.jpg", "alt.jpg"],
            ["id1", "id2"],
            reference_index=0,
        )
        assert report["success"] is True
        assert report["file_count"] == 2
        assert len(report["comparisons"]) == 2
        assert report["comparisons"][0]["is_reference"] is True
        assert report["comparisons"][1]["fully_matches"] is False

    def test_client_payload_is_slim(self, sample_jpg, sample_jpg_alt):
        report = build_comparison_report(
            [sample_jpg, sample_jpg_alt],
            ["ref.jpg", "alt.jpg"],
            ["id1", "id2"],
        )
        struct = report["structures"][0]
        assert "markers" not in struct
        assert "path" not in struct
        assert "comparison_markers" in struct
        for marker in struct["comparison_markers"]:
            assert "offset" not in marker
            assert "segment_length" not in marker
        for row in report["comparisons"]:
            for cell in row.get("cells") or []:
                assert "reference_marker" not in cell
                assert "candidate_marker" not in cell


EXEMPLO3_7JPG = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "images"
    / "exemplo3_7.jpg"
)


class TestJpegStructureMatrix:
    def test_all_pairs_matrix_diagonal_match(self, sample_jpg, sample_jpg_alt):
        report = build_similarity_matrix(
            mode="all_pairs",
            questioned_paths=[sample_jpg, sample_jpg_alt],
            questioned_labels=["a.jpg", "b.jpg"],
            questioned_ids=["id-a", "id-b"],
        )
        assert report["success"] is True
        matrix = report["matrix"]
        assert len(matrix["rows"]) == 2
        assert matrix["rows"][0]["cells"][0]["matches"] is True
        assert matrix["rows"][1]["cells"][1]["matches"] is True

    def test_with_reference_matrix_shape(self, sample_jpg, sample_jpg_alt):
        report = build_similarity_matrix(
            mode="with_reference",
            reference_paths=[sample_jpg],
            reference_labels=["ref.jpg"],
            reference_ids=["ref-id"],
            questioned_paths=[sample_jpg, sample_jpg_alt],
            questioned_labels=["q1.jpg", "q2.jpg"],
            questioned_ids=["q1", "q2"],
        )
        assert report["success"] is True
        assert report["reference_count"] == 1
        assert report["questioned_count"] == 2
        assert len(report["matrix"]["rows"]) == 1
        assert len(report["matrix"]["rows"][0]["cells"]) == 2
        assert report["matrix"]["rows"][0]["cells"][0]["matches"] is True

    def test_dht_content_ignored_in_compare(self, sample_jpg):
        dump_a = dump_jpeg_structure(sample_jpg)
        dump_b = dump_jpeg_structure(sample_jpg)
        for marker in dump_b["comparison_markers"]:
            if marker.get("name") == "DHT" and marker.get("dht_tables"):
                marker["dht_tables"][0]["values"] = [255, 254, 253]
        result = compare_jpeg_structures(dump_a, dump_b)
        assert result["fully_matches"] is True

    def test_matrix_agrees_with_slim_structure_compare(self, sample_jpg, sample_jpg_alt):
        report = build_similarity_matrix(
            mode="with_reference",
            reference_paths=[sample_jpg],
            reference_labels=["ref.jpg"],
            reference_ids=["ref-id"],
            questioned_paths=[sample_jpg, sample_jpg_alt],
            questioned_labels=["q1.jpg", "q2.jpg"],
            questioned_ids=["q1", "q2"],
        )
        ref_slim = report["reference_structures"][0]
        for j, q_slim in enumerate(report["questioned_structures"]):
            matrix_match = report["matrix"]["rows"][0]["cells"][j]["matches"]
            cmp = compare_jpeg_structures(ref_slim, q_slim)
            assert matrix_match == cmp["fully_matches"]


class TestExemplo3Regression:
    @pytest.mark.skipif(not EXEMPLO3_7JPG.is_file(), reason="7.jpg do caso Exemplo3 ausente")
    def test_exemplo3_7jpg_app_thumbnail_with_rst_does_not_keyerror(self):
        """Regressão: APP1(Exif) com thumbnail contendo RST colapsado."""
        dump = dump_jpeg_structure(str(EXEMPLO3_7JPG))
        assert dump["available"] is True
        app1 = next(
            (m for m in dump["comparison_markers"] if m.get("name") == "APP1"),
            None,
        )
        assert app1 is not None
        assert app1.get("has_thumbnail") is True
        thumb_markers = (app1.get("thumbnail") or {}).get("markers") or []
        for marker in thumb_markers:
            assert marker.get("display_name") or marker.get("name")
        report = build_comparison_report(
            [str(EXEMPLO3_7JPG)],
            ["7.jpg"],
            ["7cd98cb4"],
        )
        assert report["success"] is True


# --- markers (ex test_jpeg_markers) ---


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


# --- grid export (ex test_jpeg_structure_grid_export) ---


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


# --- matrix export (ex test_jpeg_structure_matrix_export) ---


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
