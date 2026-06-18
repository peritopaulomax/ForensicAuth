"""Layout Graphviz do grafo estrutural PDF (notebook estrutura_pdf_metricas)."""

import pytest
import fitz
import networkx as nx

from core.legacy.pdf.pdf_structure_graph import (
    analyze_pdf_structure,
    compute_graphviz_positions,
    render_graph_html,
)


@pytest.fixture
def sample_pdf(tmp_path):
    pdf_path = tmp_path / "sample.pdf"
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "PDF structure graph test.")
    doc.save(str(pdf_path))
    doc.close()
    return str(pdf_path)


def _graphviz_available() -> bool:
    g = nx.DiGraph()
    g.add_edge("a", "b")
    try:
        compute_graphviz_positions(g)
        return True
    except RuntimeError:
        return False


@pytest.mark.skipif(not _graphviz_available(), reason="Graphviz/pydot nao instalado")
class TestPDFStructureGraphLayout:
    def test_dot_layout_is_hierarchical_tb(self):
        g = nx.DiGraph()
        g.add_edge("root", "child")
        pos, engine = compute_graphviz_positions(g)
        assert engine.startswith("graphviz_dot")
        assert pos["root"][1] > pos["child"][1]

    def test_analyze_produces_png_and_layout_engine(self, sample_pdf, tmp_path):
        out = analyze_pdf_structure(sample_pdf, tmp_path)
        assert out["layout_engine"].startswith("graphviz_dot")
        assert (tmp_path / "structure_graph.png").exists()
        assert out["nodes"] >= 1
        if out.get("structure_graph_html_error"):
            pytest.skip(out["structure_graph_html_error"])
        assert out.get("structure_graph_html_path")
        assert (tmp_path / "structure_graph.html").exists()

    def test_html_includes_pyvis_configure_panel(self, sample_pdf, tmp_path):
        from core.legacy.pdf.pdf_structure_graph import parse_pdf_structure

        graph = parse_pdf_structure(sample_pdf)
        pos, _ = compute_graphviz_positions(graph)
        html_path = tmp_path / "structure_graph.html"
        err = render_graph_html(graph, html_path, pos=pos)
        if err:
            pytest.skip(err)
        html = html_path.read_text(encoding="utf-8")
        assert "configure" in html.lower()
        assert '"physics"' in html or "'physics'" in html
        # show_buttons exige options.configure antes de atribuir container ao #config
        assert '"configure"' in html
        assert 'options.configure["container"]' in html
