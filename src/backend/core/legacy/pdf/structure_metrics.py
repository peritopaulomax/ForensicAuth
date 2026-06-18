"""Pipeline de metricas estruturais de PDF."""

from core.legacy.pdf.pdf_structure_graph import (
    analyze_pdf_structure,
    compute_graphviz_positions,
    parse_pdf_structure,
    render_graph_html,
    render_graph_png,
)

__all__ = [
    "analyze_pdf_structure",
    "compute_graphviz_positions",
    "parse_pdf_structure",
    "render_graph_html",
    "render_graph_png",
]
