"""Testes unitarios do parser ISO BMFF."""

from __future__ import annotations

import struct
from pathlib import Path

from core.legacy.video.isom_parser import parse_iso_base_media, run_isomedia_parser


def _box(box_type: str, payload: bytes) -> bytes:
    return struct.pack(">I4s", 8 + len(payload), box_type.encode("ascii")) + payload


def _extended_box(box_type: str, payload: bytes) -> bytes:
    size = 16 + len(payload)
    return struct.pack(">I4sQ", 1, box_type.encode("ascii"), size) + payload


def _lang_code(code: str) -> int:
    a, b, c = (ord(code[0]) - 0x60, ord(code[1]) - 0x60, ord(code[2]) - 0x60)
    return (a << 10) | (b << 5) | c


def _make_minimal_mp4(path: Path, *, with_extended: bool = False) -> None:
    ftyp = _box("ftyp", b"isom" + struct.pack(">I", 512) + b"isomiso2")

    mvhd_payload = b"\x00\x00\x00\x00" + struct.pack(">IIII", 1, 2, 1000, 5000)
    mvhd = _box("mvhd", mvhd_payload)

    tkhd_payload = b"\x00\x00\x00\x07" + struct.pack(">IIIII", 1, 2, 1, 0, 4000)
    tkhd = _box("tkhd", tkhd_payload)

    mdhd_payload = b"\x00\x00\x00\x00" + struct.pack(">IIIIH", 1, 2, 48000, 96000, _lang_code("eng"))
    mdhd = _box("mdhd", mdhd_payload)

    hdlr_payload = (
        b"\x00\x00\x00\x00"
        + struct.pack(">I", 0)
        + b"vide"
        + struct.pack(">III", 0, 0, 0)
        + b"VideoHandler\x00"
    )
    hdlr = _box("hdlr", hdlr_payload)
    stbl = _box("stbl", b"")
    minf = _box("minf", stbl)
    mdia = _box("mdia", mdhd + hdlr + minf)
    trak = _box("trak", tkhd + mdia)

    udta = _box("udta", b"Creator=UnitTest")
    meta = _box("meta", b"\x00\x00\x00\x00" + b"json:{\"source\":\"unit\"}")

    moov_payload = mvhd + trak + udta + meta
    if with_extended:
        moov_payload += _extended_box("uuid", b"EXTENDED")
    moov = _box("moov", moov_payload)

    mdat = _box("mdat", b"\x00" * 32)
    path.write_bytes(ftyp + moov + mdat)


def test_isom_parser_extracts_structure_and_metadata(tmp_path: Path):
    sample = tmp_path / "original.mp4"
    _make_minimal_mp4(sample)

    graph = parse_iso_base_media(str(sample))
    node_types = {data.get("type") for _, data in graph.nodes(data=True)}
    assert {"ftyp", "moov", "trak", "mdat"}.issubset(node_types)

    out = run_isomedia_parser(str(sample), tmp_path / "out")
    metadata = out.get("metadata") or {}
    assert metadata.get("timescale") == 1000
    assert metadata.get("duration") == 5000
    assert metadata.get("creation_time") == 1
    assert (tmp_path / "out" / "isom_tree.txt").exists()
    assert (tmp_path / "out" / "isom_structure_graph.json").exists()
    assert len(out.get("udta_atoms") or []) >= 1
    assert len(out.get("meta_atoms") or []) >= 1

    udta = out["udta_atoms"][0]
    assert "preview_hex_dump" in udta
    assert "|Creator=UnitTest|" in udta["preview_hex_dump"]
    assert "43 72 65 61" in udta["preview_hex_dump"]


def test_hex_dump_with_ascii_helper():
    from core.legacy.video.isom_parser import _hex_dump_with_ascii

    dump = _hex_dump_with_ascii(b"Creator=UnitTest")
    assert "|Creator=UnitTest|" in dump["text"]
    assert dump["lines"][0]["ascii"].startswith("Creator")


def test_isom_parser_supports_extended_size_box(tmp_path: Path):
    sample = tmp_path / "extended.mp4"
    _make_minimal_mp4(sample, with_extended=True)

    graph = parse_iso_base_media(str(sample))
    uuid_nodes = [data for _, data in graph.nodes(data=True) if data.get("type") == "uuid"]
    assert uuid_nodes, "esperava box uuid com tamanho estendido"
    assert uuid_nodes[0].get("extended_size") is True
    assert int(uuid_nodes[0].get("size", 0)) == 16 + len(b"EXTENDED")
