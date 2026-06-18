"""Testes do extrator de metadados de imagem."""

import os
import subprocess
import tempfile

import pytest
from PIL import Image

from core.metadata.extractor import extract_image_metadata
from core.metadata.jpeg_structure import read_jpeg_structure


def _write_sample_jpg(path: str) -> None:
    Image.new("RGB", (80, 80), color="blue").save(path, "JPEG", quality=90)
    try:
        subprocess.run(
            [
                "exiftool",
                "-EXIF:Make=NIKON CORPORATION",
                "-EXIF:Model=NIKON D70s",
                "-EXIF:Software=Test Suite",
                "-overwrite_original",
                path,
            ],
            check=True,
            capture_output=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass


@pytest.fixture
def sample_jpg():
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        path = f.name
    _write_sample_jpg(path)
    yield path
    os.unlink(path)


class TestMetadataExtractor:
    def test_extract_jpeg_structure(self, sample_jpg):
        struct = read_jpeg_structure(sample_jpg)
        assert struct["available"] is True
        assert len(struct["quantization_tables"]) >= 1
        assert struct["quantization_tables"][0]["matrix"]

    def test_extract_full_payload(self, sample_jpg):
        result = extract_image_metadata(sample_jpg)
        assert result["success"] is True
        assert result["summary"]["is_jpeg"] is True
        assert "exif" in result["metadata"]["families"]
        engines = result["metadata"]["engines"] or []
        assert "pillow" in engines
        assert "xmp_sniff" in engines
        assert "pillow_icc" in engines

    def test_payload_includes_forensic_insights(self, sample_jpg):
        result = extract_image_metadata(sample_jpg)
        assert "forensic_insights" in result
        assert isinstance(result["forensic_insights"], list)
        assert result["forensic_insights"]

    def test_exif_entries_include_hints(self, sample_jpg):
        from core.metadata.extractor import _tag_entry

        direct = _tag_entry("EXIF:Make", "NIKON CORPORATION", "exiftool")
        assert direct["group"] == "exif"
        assert direct.get("hint")

        result = extract_image_metadata(sample_jpg)
        exif_entries = result["metadata"]["families"]["exif"]
        if exif_entries:
            assert any(e.get("hint") for e in exif_entries)

    def test_combined_runs_exiftool_and_pillow(self, sample_jpg):
        from core.metadata.extractor import _exiftool_available

        result = extract_image_metadata(sample_jpg)
        engines = result["metadata"].get("engines") or []
        assert "pillow" in engines
        assert "xmp_sniff" in engines
        assert "pillow_icc" in engines
        if _exiftool_available():
            assert "exiftool" in engines
            sources = {
                e.get("source")
                for fam in result["metadata"]["families"].values()
                for e in fam
            }
            assert "exiftool" in sources

    def test_exiftool_reads_jpeg_when_available(self, sample_jpg):
        from core.metadata.extractor import _exiftool_available, _read_exiftool

        if not _exiftool_available():
            pytest.skip("exiftool binary nao instalado")
        meta = _read_exiftool(sample_jpg)
        assert meta["engine"] == "exiftool"
        assert meta["available"] is True
        total = sum(len(v) for v in meta["families"].values())
        assert total > 0

    def test_png_no_jpeg_structure(self):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            Image.new("RGB", (40, 40), color="green").save(f.name, "PNG")
            path = f.name
        try:
            result = extract_image_metadata(path)
            assert result["success"] is True
            assert result["jpeg_structure"]["available"] is False
        finally:
            os.unlink(path)
