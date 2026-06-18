"""Testes do dicionário de significados de propriedades XMP/EXIF."""

from core.metadata.xmp_property_hints import property_hint


class TestPropertyHint:
    def test_resolves_by_local_name(self):
        assert property_hint("DateTimeOriginal")
        assert "captura" in property_hint("DateTimeOriginal").lower()

    def test_resolves_by_qname_prefix(self):
        assert property_hint("exif:ColorSpace")
        assert "sRGB" in property_hint("exif:ColorSpace")

    def test_resolves_compound_path_tail(self):
        assert property_hint("Flash.Fired")
        assert "flash" in property_hint("Flash.Fired").lower()

    def test_rdf_description_element_hint(self):
        hint = property_hint("Description", element_name="Description")
        assert hint and "RDF" in hint

    def test_unknown_property_returns_none(self):
        assert property_hint("TotallyUnknownTagXYZ") is None
