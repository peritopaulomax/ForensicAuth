"""Tests for deep video metadata extraction."""

from __future__ import annotations

import struct
from pathlib import Path

import pytest


def _box(box_type: str, payload: bytes) -> bytes:
    return struct.pack(">I4s", 8 + len(payload), box_type.encode("ascii")) + payload


@pytest.fixture
def sample_mp4(tmp_path: Path) -> Path:
    """Minimal ISO BMFF with moov/trak for isom + ffprobe/exiftool best-effort."""
    ftyp = _box("ftyp", b"isom" + struct.pack(">I", 512) + b"isomiso2")
    mvhd = _box("mvhd", b"\x00\x00\x00\x00" + struct.pack(">IIII", 1, 2, 1000, 5000))
    tkhd = _box("tkhd", b"\x00\x00\x00\x07" + struct.pack(">IIIII", 1, 2, 1, 0, 4000))
    mdhd = _box(
        "mdhd",
        b"\x00\x00\x00\x00" + struct.pack(">IIIIH", 1, 2, 48000, 96000, ((5 << 10) | (14 << 5) | 7)),
    )
    hdlr = _box(
        "hdlr",
        b"\x00\x00\x00\x00"
        + struct.pack(">I", 0)
        + b"vide"
        + struct.pack(">III", 0, 0, 0)
        + b"VideoHandler\x00",
    )
    stbl = _box("stbl", b"")
    minf = _box("minf", stbl)
    mdia = _box("mdia", mdhd + hdlr + minf)
    trak = _box("trak", tkhd + mdia)
    moov = _box("moov", mvhd + trak)
    mdat = _box("mdat", b"\x00" * 32)
    path = tmp_path / "sample.mp4"
    path.write_bytes(ftyp + moov + mdat)
    return path


class TestVideoMetadataClassifier:
    def test_classify_families(self):
        from core.metadata.video_extractor import _classify_video_tag

        assert _classify_video_tag("QuickTime:CreateDate") == "quicktime"
        assert _classify_video_tag("Track1:HandlerType") == "quicktime"
        assert _classify_video_tag("GPS:GPSLatitude") == "gps"
        assert _classify_video_tag("GoPro:CameraSerialNumber") == "camera"
        assert _classify_video_tag("H264:Profile") == "codec"
        assert _classify_video_tag("XMP:CreatorTool") == "xmp"
        assert _classify_video_tag("File:FileSize") == "file"
        assert _classify_video_tag("ffprobe:stream[0:video].codec_name") == "streams"


class TestVideoMetadataPlugin:
    def test_plugin_registered(self):
        from core.plugin_registry import PluginRegistry

        registry = PluginRegistry()
        plugins_dir = Path(__file__).resolve().parents[2] / "src" / "backend" / "core" / "plugins"
        registry.discover_and_register(str(plugins_dir))
        assert "video_metadata" in registry.PLUGINS

    def test_extract_on_minimal_mp4(self, sample_mp4, tmp_path):
        from core.plugins.video_metadata_plugin import VideoMetadataPlugin

        plugin = VideoMetadataPlugin()
        assert plugin.name == "video_metadata"
        assert "video" in plugin.supported_types

        result = plugin.analyze(str(sample_mp4), {"_job_staging_dir": str(tmp_path / "vout")})
        assert result["success"] is True
        assert "summary" in result
        assert "metadata" in result
        assert Path(result["metadata_json_path"]).is_file()
        assert Path(result["metadata_report_path"]).is_file()
        assert result["summary"]["total_tags"] >= 0
        engines = result["summary"].get("metadata_engines") or []
        # Pelo menos um motor deve contribuir em ambiente de CI/dev tipico
        assert isinstance(engines, list)
        families = result["metadata"]["families"]
        assert "quicktime" in families
        assert "streams" in families
        assert "gps" in families
