"""Unit tests for PDF forensic plugins (cards ativos)."""

import pytest
import fitz
from pathlib import Path

from core.plugin_registry import PluginRegistry, STANDBY_PLUGIN_NAMES

from core.plugins.pdf_touchup_plugin import PDFTouchupPlugin
from core.plugins.pdf_font_color_overlay_plugin import PDFFontColorOverlayPlugin
from core.legacy.pdf.pdf_forensic_scanner import resolve_page_resources, resolve_page_resources_xref
from core.legacy.pdf.pdf_font_color_overlay import collect_page_glyph_runs, run_font_color_overlay


@pytest.fixture
def sample_pdf(tmp_path):
    """Create a simple PDF with 2 pages for testing."""
    pdf_path = tmp_path / "sample.pdf"
    doc = fitz.open()

    page1 = doc.new_page()
    page1.insert_text((72, 72), "Hello PDF forensic world.")
    page1.insert_text((72, 100), "Page one content here.")

    page2 = doc.new_page()
    page2.insert_text((72, 72), "Second page of the document.")

    doc.save(str(pdf_path))
    doc.close()
    return str(pdf_path)


class TestPDFTouchupPlugin:
    def test_analyze_returns_success(self, sample_pdf):
        plugin = PDFTouchupPlugin()
        result = plugin.analyze(sample_pdf, {})
        assert result["success"] is True
        assert result["adapter"] == "pdf_touchup"

    def test_clean_pdf_not_tampered(self, sample_pdf):
        plugin = PDFTouchupPlugin()
        result = plugin.analyze(sample_pdf, {})
        assert result["is_tampered"] is False
        assert result["touchup_count"] == 0


class TestPDFFontColorOverlayPlugin:
    def test_by_family_default(self, sample_pdf, tmp_path):
        plugin = PDFFontColorOverlayPlugin()
        result = plugin.analyze(sample_pdf, {"opacity": 0.5})
        assert result["success"] is True
        assert result["mode"] == "family"

    def test_by_subset_does_not_crash(self, sample_pdf):
        plugin = PDFFontColorOverlayPlugin()
        result = plugin.analyze(sample_pdf, {"opacity": 0.5, "by_subset": True})
        assert result["success"] is True
        assert result["mode"] == "subset"

    def test_resolve_page_resources_tuple(self, sample_pdf):
        doc = fitz.open(sample_pdf)
        try:
            page = doc[0]
            res_xref, fonts, xobjects = resolve_page_resources(doc, page)
            assert res_xref is not None
            assert isinstance(fonts, dict)
            assert isinstance(xobjects, dict)
        finally:
            doc.close()

    def test_read_subresource_map_no_infinite_recursion(self, sample_pdf):
        doc = fitz.open(sample_pdf)
        try:
            page = doc[0]
            res_xref = resolve_page_resources_xref(doc, page.xref)
            assert res_xref is not None
            visited: set[int] = set()
            from core.legacy.pdf.pdf_forensic_scanner import _read_subresource_map

            _read_subresource_map(doc, res_xref, "Font", visited)
            _read_subresource_map(doc, res_xref, "Font", visited)
            _read_subresource_map(doc, res_xref, "XObject", visited)
        finally:
            doc.close()

    def test_glyph_runs_skips_page_without_resources(self, tmp_path):
        pdf_path = tmp_path / "blank.pdf"
        doc = fitz.open()
        doc.new_page()
        doc.save(str(pdf_path))
        doc.close()
        doc = fitz.open(pdf_path)
        try:
            page = doc[0]
            runs = collect_page_glyph_runs(doc, page, {})
            assert runs == []
        finally:
            doc.close()

    def test_run_overlay_image_only_pdf(self, tmp_path):
        pdf_path = tmp_path / "img_only.pdf"
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Text on page two")
        doc.new_page()
        doc.save(str(pdf_path))
        doc.close()
        out_pdf = tmp_path / "out.pdf"
        out_txt = tmp_path / "out.txt"
        meta = run_font_color_overlay(pdf_path, out_pdf, out_txt, by_subset=True)
        assert meta["fonts_count"] >= 1
        assert out_pdf.exists()


class TestPDFPluginsRegistered:
    def test_active_pdf_card_plugins_registered(self):
        registry = PluginRegistry()
        plugins_dir = Path(__file__).resolve().parents[2] / "src" / "backend" / "core" / "plugins"
        registry.discover_and_register(str(plugins_dir))
        names = registry.list_plugins()
        for technique in (
            "pdf_forensic_extract",
            "pdf_structure_metrics",
            "pdf_structure_similarity",
            "pdf_font_color_overlay",
        ):
            assert technique in names
        for standby in ("pdf_touchup", "pdf_metadata", "pdf_structure", "pdf_text_image"):
            if standby in STANDBY_PLUGIN_NAMES or standby not in names:
                continue
            pytest.fail(f"Plugin orfao {standby} ainda registrado")
