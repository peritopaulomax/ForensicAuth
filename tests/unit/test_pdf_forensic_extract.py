"""Testes de versoes incrementais e extracao PDF."""

import tempfile
from pathlib import Path

import fitz
import pytest

from core.legacy.pdf.pdf_forensic_extract import (
    _is_valid_jpeg2000_stream,
    analyze_incremental_versions,
    find_eof_end_positions,
    is_linearized,
    run_pdf_forensic_extract,
)


def _build_pdf_bytes(eof_count: int, linearized: bool = False, tail_after_each: bool = True) -> bytes:
    parts = [b"%PDF-1.4\n"]
    if linearized:
        parts.append(b"% /Linearized 1\n")
    for i in range(eof_count):
        parts.append(f"% body {i}\n".encode())
        parts.append(b"%%EOF")
        if tail_after_each and i < eof_count - 1:
            parts.append(b"\n% incremental garbage\n")
    return b"".join(parts)


def _analyze_bytes(data: bytes) -> dict:
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(data)
        path = f.name
    try:
        return analyze_incremental_versions(path)
    finally:
        Path(path).unlink(missing_ok=True)


def test_find_eof_positions():
    data = _build_pdf_bytes(2, tail_after_each=True)
    assert len(find_eof_end_positions(data)) == 2


def test_non_linearized_no_updates():
    data = _build_pdf_bytes(1, tail_after_each=False)
    assert _analyze_bytes(data)["status"] == "no_updates"


def test_non_linearized_orphan_data():
    data = _build_pdf_bytes(1, tail_after_each=False) + b"\n% lixo apos primeiro EOF\n"
    assert _analyze_bytes(data)["status"] == "orphan_data"


def test_non_linearized_two_versions():
    data = _build_pdf_bytes(2, tail_after_each=True)
    r = _analyze_bytes(data)
    assert r["version_count"] == 2


def test_linearized_ignores_first_eof():
    data = _build_pdf_bytes(2, linearized=True, tail_after_each=True)
    assert is_linearized(data)
    assert _analyze_bytes(data)["version_count"] == 1


@pytest.fixture
def sample_pdf(tmp_path):
    pdf_path = tmp_path / "sample.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "PDF extract test")
    doc.save(str(pdf_path))
    doc.close()
    return str(pdf_path)


def test_run_extract_pipeline(sample_pdf, tmp_path):
    out = run_pdf_forensic_extract(sample_pdf, tmp_path / "out")
    assert (tmp_path / "out" / "metadata_report.txt").exists()
    assert (tmp_path / "out" / "extract_manifest.json").exists()
    assert "image_count" in out


def test_is_valid_jpeg2000_stream_detects_encapsulated_formats():
    jp2_sig = b"\x00\x00\x00\x0cjP  \x0d\x0a\x87\x0a" + b"\x00" * 8
    jpx_sig = b"\x00\x00\x00\x0cjPX \x0d\x0a\x87\x0a" + b"\x00" * 8
    soc = b"\xff\x4f\xff\x51" + b"\x00" * 8
    assert _is_valid_jpeg2000_stream(jp2_sig)
    assert _is_valid_jpeg2000_stream(jpx_sig)
    assert _is_valid_jpeg2000_stream(soc)
    assert not _is_valid_jpeg2000_stream(b"not-a-jpeg2000-stream")
