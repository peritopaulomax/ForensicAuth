"""Testes do dicionário de significados EXIF/TIFF."""

from core.metadata.exif_property_hints import exif_property_hint


class TestExifPropertyHint:
    def test_resolves_exiftool_prefixed_tags(self):
        assert exif_property_hint("EXIF:ColorSpace")
        assert "sRGB" in exif_property_hint("EXIF:ColorSpace")

    def test_resolves_pillow_plain_tags(self):
        assert exif_property_hint("Make")
        assert "fabricante" in exif_property_hint("Make").lower()
        assert exif_property_hint("DateTime")
        assert exif_property_hint("Software")

    def test_covers_nikon_sample_tags(self):
        sample = (
            "EXIF:CFAPattern",
            "EXIF:ExposureCompensation",
            "EXIF:ExifImageWidth",
            "EXIF:FocalLengthIn35mmFormat",
            "EXIF:InteropIndex",
            "EXIF:ThumbnailOffset",
            "EXIF:UserComment",
            "ExifOffset",
        )
        for tag in sample:
            assert exif_property_hint(tag), f"sem hint para {tag}"

    def test_gps_tags(self):
        assert exif_property_hint("GPS:GPSLatitude")
        assert exif_property_hint("GPSLatitude")

    def test_unknown_returns_none_or_fallback(self):
        assert exif_property_hint("EXIF:DateTimeOriginal")
        assert exif_property_hint("TotallyUnknownExifTagXYZ") is None
