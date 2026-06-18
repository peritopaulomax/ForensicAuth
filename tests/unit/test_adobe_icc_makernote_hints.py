"""Testes dos dicionários Adobe, ICC e MakerNotes."""

from core.metadata.adobe_property_hints import adobe_property_hint
from core.metadata.extractor import _tag_entry
from core.metadata.icc_property_hints import icc_property_hint
from core.metadata.makernote_property_hints import makernote_property_hint


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
