"""Testes unitarios de similaridade estrutural ISO BMFF."""

from __future__ import annotations

import json
import struct
from pathlib import Path

from core.legacy.video.isom_parser import parse_iso_base_media
from core.legacy.video.isom_similarity import (
    calculate_structural_similarity_and_differences,
    run_similarity_analysis,
)


def _box(box_type: str, payload: bytes) -> bytes:
    return struct.pack(">I4s", 8 + len(payload), box_type.encode("ascii")) + payload


def _lang_code(code: str) -> int:
    a, b, c = (ord(code[0]) - 0x60, ord(code[1]) - 0x60, ord(code[2]) - 0x60)
    return (a << 10) | (b << 5) | c


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
