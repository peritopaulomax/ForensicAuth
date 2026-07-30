"""Dicionários de significados: EXIF/TIFF, XMP, Adobe, ICC e MakerNotes.

MERGE mecânico (Fase 3b) de:
  test_exif_property_hints.py
  test_xmp_property_hints.py
  test_adobe_icc_makernote_hints.py
"""

from __future__ import annotations

from core.metadata.adobe_property_hints import adobe_property_hint
from core.metadata.exif_property_hints import exif_property_hint
from core.metadata.extractor import _tag_entry
from core.metadata.icc_property_hints import icc_property_hint
from core.metadata.makernote_property_hints import makernote_property_hint
from core.metadata.xmp_property_hints import property_hint


# --- EXIF / TIFF ---


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


# --- XMP ---


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


# --- Adobe / ICC / MakerNotes ---


class TestAdobePropertyHint:
    def test_photoshop_sample_tags(self):
        sample = (
            "Photoshop:ReaderName",
            "Photoshop:WriterName",
            "Photoshop:IPTCDigest",
            "Photoshop:HasRealMergedData",
            "Photoshop:SlicesGroupName",
            "Photoshop:ProgressiveScans",
        )
        for tag in sample:
            assert adobe_property_hint(tag), f"sem hint para {tag}"

    def test_tag_entry_adobe_group(self):
        entry = _tag_entry("Photoshop:ReaderName", "Adobe Photoshop CS4", "exiftool")
        assert entry["group"] == "adobe"
        assert entry.get("hint")


class TestIccPropertyHint:
    def test_icc_profile_sample_tags(self):
        sample = (
            "ICC_Profile:ProfileDescription",
            "ICC_Profile:ProfileClass",
            "ICC_Profile:MediaWhitePoint",
            "ICC_Profile:RedTRC",
            "ICC_Profile:RenderingIntent",
            "ICC:ProfileSummary",
        )
        for tag in sample:
            assert icc_property_hint(tag), f"sem hint para {tag}"

    def test_tag_entry_icc_group(self):
        entry = _tag_entry("ICC_Profile:DeviceModelDesc", "IEC 61966-2.1 sRGB", "exiftool")
        assert entry["group"] == "icc"
        assert entry.get("hint")


class TestMakernotePropertyHint:
    def test_nikon_specific_tags(self):
        assert makernote_property_hint("Nikon:ShutterCount")
        assert makernote_property_hint("Nikon:ProgramShift")

    def test_canon_specific_tags(self):
        assert makernote_property_hint("Canon:OwnerName")
        assert makernote_property_hint("Canon:PictureStyle")

    def test_generic_fallback(self):
        assert makernote_property_hint("Nikon:ISO")
        assert makernote_property_hint("Sony:FocusMode")

    def test_tag_entry_makernotes_group(self):
        entry = _tag_entry("Nikon:ISO", "400", "exiftool")
        assert entry["group"] == "makernotes"
        assert entry.get("hint")

    def test_unknown_manufacturer_tag_may_be_none(self):
        assert makernote_property_hint("Nikon:TotallyUnknownMakerTagXYZ") is None
