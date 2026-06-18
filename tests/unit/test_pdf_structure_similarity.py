"""Similaridade de grafos estruturais PDF."""

import pytest
import fitz
import networkx as nx

from core.legacy.pdf.pdf_structure_similarity import (
    compute_jaccard_cross,
    compute_jaccard_square,
    compute_wl_cross_kernel,
    graph_jaccard_similarity,
    run_similarity_analysis,
)
from core.legacy.pdf.pdf_structure_graph import parse_pdf_structure


@pytest.fixture
def sample_pdf(tmp_path):
    pdf_path = tmp_path / "sample.pdf"
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "PDF similarity test.")
    doc.save(str(pdf_path))
    doc.close()
    return str(pdf_path)


def test_jaccard_identical_graphs():
    g = nx.DiGraph()
    g.add_node("a", label="A")
    g.add_edge("a", "b", key="/K")
    assert graph_jaccard_similarity(g, g) == pytest.approx(1.0)


def test_cross_matrix_shape():
    g1 = nx.DiGraph()
    g1.add_node("x", label="X")
    g2 = nx.DiGraph()
    g2.add_node("y", label="Y")
    m = compute_jaccard_cross([g1], [g2])
    assert m.shape == (1, 1)
    wl = compute_wl_cross_kernel([g1], [g2], iterations=1)
    assert wl.shape == (1, 1)


def test_all_pairs_pipeline(sample_pdf, tmp_path):
    out = run_similarity_analysis(
        mode="all_pairs",
        reference_paths=[],
        reference_labels=[],
        questioned_paths=[sample_pdf, sample_pdf],
        questioned_labels=["a.pdf", "b.pdf"],
        out_dir=tmp_path / "out",
    )
    assert (tmp_path / "out" / "similarity_jaccard.png").exists()
    assert (tmp_path / "out" / "similarity_wl_kernel.png").exists()
    assert out.get("similarity_jaccard_image_path")


def test_with_reference_pipeline(sample_pdf, tmp_path):
    g = parse_pdf_structure(sample_pdf)
    assert g.number_of_nodes() >= 1
    out = run_similarity_analysis(
        mode="with_reference",
        reference_paths=[sample_pdf],
        reference_labels=["ref-long-name.pdf"],
        questioned_paths=[sample_pdf],
        questioned_labels=["quest-long-name.pdf"],
        out_dir=tmp_path / "cross",
    )
    assert (tmp_path / "cross" / "similarity_jaccard.png").exists()
    m = __import__("json").loads((tmp_path / "cross" / "similarity_matrices.json").read_text(encoding="utf-8"))
    j = m["metrics"]["jaccard"]["matrix"]
    assert len(j) == 1 and len(j[0]) == 1
    assert m["metrics"]["jaccard"]["row_short_labels"] == ["Q1"]
    assert m["metrics"]["jaccard"]["col_short_labels"] == ["R1"]
    assert m["metrics"]["jaccard"]["row_legend"][0]["filename"] == "quest-long-name.pdf"


def test_all_pairs_uses_pdf_refs(sample_pdf, tmp_path):
    run_similarity_analysis(
        mode="all_pairs",
        reference_paths=[],
        reference_labels=[],
        questioned_paths=[sample_pdf, sample_pdf],
        questioned_labels=["alpha-very-long.pdf", "beta-very-long.pdf"],
        out_dir=tmp_path / "pairs",
    )
    m = __import__("json").loads((tmp_path / "pairs" / "similarity_matrices.json").read_text(encoding="utf-8"))
    assert m["metrics"]["jaccard"]["row_short_labels"] == ["PDF 1", "PDF 2"]
    assert m["metrics"]["jaccard"]["row_legend"][1]["ref"] == "PDF 2"
