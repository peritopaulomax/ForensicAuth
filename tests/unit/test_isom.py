"""ISO BMFF: parser estrutural e similaridade.

MERGE mecânico (Fase 3c) de:
  test_isom_parser.py
  test_isom_similarity.py
"""

from __future__ import annotations

import json
import struct
from pathlib import Path

from forensics.video.isom_parser import parse_iso_base_media, run_isomedia_parser
from forensics.video.isom_similarity import (
    calculate_structural_similarity_and_differences,
    run_similarity_analysis,
)


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


def _make_video(path: Path, *, include_udta: bool, include_meta: bool) -> None:
    ftyp = _box("ftyp", b"isom" + struct.pack(">I", 512) + b"isomiso2")
    mvhd = _box("mvhd", b"\x00\x00\x00\x00" + struct.pack(">IIII", 1, 2, 1000, 5000))
    tkhd = _box("tkhd", b"\x00\x00\x00\x07" + struct.pack(">IIIII", 1, 2, 1, 0, 4000))
    mdhd = _box("mdhd", b"\x00\x00\x00\x00" + struct.pack(">IIIIH", 1, 2, 48000, 96000, _lang_code("eng")))
    hdlr = _box(
        "hdlr",
        b"\x00\x00\x00\x00" + struct.pack(">I", 0) + b"vide" + struct.pack(">III", 0, 0, 0) + b"VideoHandler\x00",
    )
    stbl = _box("stbl", _box("stts", b"") + _box("stco", b""))
    minf = _box("minf", stbl)
    mdia = _box("mdia", mdhd + hdlr + minf)
    trak = _box("trak", tkhd + mdia)
    moov_payload = mvhd + trak
    if include_udta:
        moov_payload += _box("udta", b"Device=A")
    if include_meta:
        moov_payload += _box("meta", b"\x00\x00\x00\x00meta=a")
    moov = _box("moov", moov_payload)
    mdat = _box("mdat", b"\x01" * 24)
    path.write_bytes(ftyp + moov + mdat)


# --- parser ---


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
    from forensics.video.isom_parser import _hex_dump_with_ascii

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


# --- similarity ---


def test_isom_similarity_exact_match(tmp_path: Path):
    q = tmp_path / "q.mp4"
    r = tmp_path / "r.mp4"
    _make_video(q, include_udta=True, include_meta=True)
    _make_video(r, include_udta=True, include_meta=True)

    gq = parse_iso_base_media(str(q))
    gr = parse_iso_base_media(str(r))
    sim, diffs = calculate_structural_similarity_and_differences(gq, gr)
    assert sim == 1.0
    assert diffs == []

    out = run_similarity_analysis(
        mode="with_reference",
        reference_paths=[str(r)],
        reference_labels=["ref.mp4"],
        questioned_paths=[str(q)],
        questioned_labels=["quest.mp4"],
        out_dir=tmp_path / "out",
    )
    assert (tmp_path / "out" / "similarity_jaccard.png").exists()
    payload = json.loads((tmp_path / "out" / "similarity_matrices.json").read_text(encoding="utf-8"))
    matrix = payload["metrics"]["jaccard"]["matrix"]
    assert matrix[0][0] == 1.0
    assert out.get("similarity_jaccard_image_path")


def test_isom_similarity_detects_structural_difference(tmp_path: Path):
    q = tmp_path / "questioned.mp4"
    r = tmp_path / "reference.mp4"
    _make_video(q, include_udta=False, include_meta=False)
    _make_video(r, include_udta=True, include_meta=True)

    gq = parse_iso_base_media(str(q))
    gr = parse_iso_base_media(str(r))
    sim, diffs = calculate_structural_similarity_and_differences(gq, gr)
    assert sim < 1.0
    assert len(diffs) > 0
