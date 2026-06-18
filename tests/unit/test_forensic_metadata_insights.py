"""Testes dos alertas forenses automáticos e deduplicação."""

from core.metadata.extractor import _dedupe_family_entries, _normalize_tag_for_dedup
from core.metadata.forensic_metadata_insights import build_forensic_insights


class TestDedupeFamilyEntries:
    def test_merges_same_tag_and_value_different_sources(self):
        entries = [
            {"tag": "Make", "value": "NIKON CORPORATION", "source": "pillow", "group": "exif"},
            {"tag": "EXIF:Make", "value": "NIKON CORPORATION", "source": "exiftool", "group": "exif"},
        ]
        merged = _dedupe_family_entries(entries)
        assert len(merged) == 1
        assert "pillow" in merged[0]["source"]
        assert "exiftool" in merged[0]["source"]

    def test_keeps_different_values(self):
        entries = [
            {"tag": "XResolution", "value": "300", "source": "pillow"},
            {"tag": "EXIF:XResolution", "value": "300.0", "source": "exiftool"},
        ]
        merged = _dedupe_family_entries(entries)
        assert len(merged) == 2

    def test_normalize_tag_for_dedup(self):
        assert _normalize_tag_for_dedup("EXIF:Make") == "make"
        assert _normalize_tag_for_dedup("Make") == "make"


class TestForensicInsights:
    def test_detects_edit_after_capture_and_photoshop(self):
        families = {
            "exif": [
                {"tag": "EXIF:DateTimeOriginal", "value": "2012:05:15 11:25:05"},
                {"tag": "EXIF:ModifyDate", "value": "2012:05:15 12:31:40"},
                {"tag": "EXIF:Software", "value": "Adobe Photoshop CS4 Windows"},
            ],
            "adobe": [],
            "makernotes": [],
            "xmp": [],
            "iptc": [],
            "icc": [],
            "other": [],
        }
        xmp = {
            "available": True,
            "property_count": 3,
            "packet_sha256": "abc123",
            "semantic_groups": [
                {
                    "namespace_label": "ResourceEvent",
                    "namespace_uri": "http://example/",
                    "properties": [
                        {"name": "stEvt:action", "value": "created"},
                        {"name": "stEvt:softwareAgent", "value": "Adobe Photoshop CS4 Windows"},
                        {"name": "stEvt:when", "value": "2012-05-15T12:31:40-03:00"},
                    ],
                }
            ],
        }
        summary = {"has_gps": False, "has_makernotes": False, "tag_counts": {"makernotes": 0}}
        alerts = build_forensic_insights(families, xmp, summary)
        titles = [a["title"] for a in alerts]
        assert "Arquivo modificado após a captura" in titles
        assert "Software de edição detectado" in titles
        assert "Histórico de edição XMP (Photoshop/Camera Raw)" in titles

    def test_returns_info_when_no_strong_signals(self):
        families = {k: [] for k in ("exif", "iptc", "xmp", "icc", "makernotes", "adobe", "other")}
        alerts = build_forensic_insights(families, {}, {})
        assert alerts
        assert any("Nenhum alerta automático" in a["title"] for a in alerts)

    def test_ignores_filesystem_filemodifydate(self):
        """File:FileModifyDate (upload/cópia) não deve disparar alerta de edição."""
        families = {
            "exif": [
                {"tag": "EXIF:CreateDate", "value": "2012:10:07 13:08:39"},
                {"tag": "EXIF:DateTimeOriginal", "value": "2012:10:07 13:08:39"},
            ],
            "other": [
                {"tag": "File:FileModifyDate", "value": "2026:06:08 11:43:15"},
                {"tag": "File:FileAccessDate", "value": "2026:06:08 11:43:15"},
            ],
            "iptc": [],
            "xmp": [],
            "icc": [],
            "makernotes": [],
            "adobe": [],
        }
        alerts = build_forensic_insights(families, {}, {})
        titles = [a["title"] for a in alerts]
        assert "Arquivo modificado após a captura" not in titles

    def test_detects_internal_exif_modify_after_capture(self):
        families = {
            "exif": [
                {"tag": "EXIF:DateTimeOriginal", "value": "2012:05:15 11:25:05"},
                {"tag": "EXIF:ModifyDate", "value": "2012:05:15 12:31:40"},
            ],
            "iptc": [],
            "xmp": [],
            "icc": [],
            "makernotes": [],
            "adobe": [],
            "other": [],
        }
        alerts = build_forensic_insights(families, {}, {})
        assert "Arquivo modificado após a captura" in [a["title"] for a in alerts]
