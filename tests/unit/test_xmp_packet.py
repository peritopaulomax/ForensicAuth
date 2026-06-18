"""Testes do extrator de pacote XMP estruturado."""

import os
import subprocess
import tempfile

import pytest
from PIL import Image

from core.metadata.xmp_packet import extract_xmp_packet, _parse_xmp_packet


def _write_xmp_jpeg(path: str) -> None:
    Image.new("RGB", (80, 80), color="red").save(path, "JPEG", quality=90)
    subprocess.run(
        [
            "exiftool",
            "-XMP:CreatorTool=Ver.1.00",
            "-XMP:CreateDate=2012:05:15 11:25:05-03:00",
            "-overwrite_original",
            path,
        ],
        check=True,
        capture_output=True,
    )


@pytest.fixture
def sample_xmp_jpg():
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        path = f.name
    _write_xmp_jpeg(path)
    yield path
    os.unlink(path)


class TestXmpPacket:
    def test_parse_xmp_packet_builds_semantic_groups(self, sample_xmp_jpg):
        from core.metadata.xmp_packet import _read_xmp_packet_bytes

        packet = _read_xmp_packet_bytes(sample_xmp_jpg)
        assert packet is not None
        parsed = _parse_xmp_packet(packet)
        assert parsed["available"] is True
        assert parsed["packet_xml"]
        assert parsed["packet_sha256"]
        tree = parsed["structural_tree"]
        assert tree["name"] == "xmpmeta"
        # Atributos XMP em rdf:Description viram nós filhos, não inline
        rdf = next(c for c in tree["children"] if c["name"] == "RDF")
        desc = next(c for c in rdf["children"] if c["name"] == "Description")
        child_names = [c["name"] for c in desc["children"]]
        assert "CreatorTool" in child_names
        assert parsed["property_count"] >= 2
        names = [p["name"] for g in parsed["semantic_groups"] for p in g["properties"]]
        assert any("CreatorTool" in n for n in names)
        assert any("CreateDate" in n for n in names)

    def test_extract_xmp_packet_integration(self, sample_xmp_jpg):
        from core.metadata.xmp_packet import _exiftool_available

        if not _exiftool_available():
            pytest.skip("exiftool binary nao instalado")

        result = extract_xmp_packet(sample_xmp_jpg)
        assert result["available"] is True
        assert result["source"] == "exiftool"
        assert result["packet_sha256"]
        assert len(result["semantic_groups"]) >= 1

    def test_extract_image_metadata_includes_xmp_structured(self, sample_xmp_jpg):
        from core.metadata.extractor import extract_image_metadata

        payload = extract_image_metadata(sample_xmp_jpg)
        assert payload["success"] is True
        xmp = payload.get("xmp_structured") or {}
        assert xmp.get("available") is True
        assert payload["summary"].get("has_xmp_packet") is True
        assert payload["metadata"].get("xmp_structured", {}).get("available") is True
