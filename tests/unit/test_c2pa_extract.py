"""Testes de extração/validação C2PA (Content Credentials)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from PIL import Image

from core.metadata.c2pa_extract import (
    c2pa_runtime_status,
    extract_c2pa_manifest,
    is_c2pa_exiftool_tag,
)
from core.metadata.extractor import extract_image_metadata
from core.metadata.forensic_metadata_insights import build_forensic_insights

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "c2pa_sample.jpg"


def test_is_c2pa_exiftool_tag():
    assert is_c2pa_exiftool_tag("JUMBF:JUMDLabel")
    assert is_c2pa_exiftool_tag("Jpeg2000:C2paThumbnailClaimJpegType")
    assert is_c2pa_exiftool_tag("C2PA:ClaimGenerator")
    assert not is_c2pa_exiftool_tag("EXIF:Make")
    assert not is_c2pa_exiftool_tag("XMP:CreatorTool")


def test_c2pa_absent_on_plain_jpeg(tmp_path):
    path = tmp_path / "plain.jpg"
    Image.new("RGB", (48, 48), "green").save(path, "JPEG")
    ok, _ = c2pa_runtime_status()
    if not ok:
        pytest.skip("c2pa-python nao instalado")
    result = extract_c2pa_manifest(str(path))
    assert result["available"] is True
    assert result["present"] is False
    assert result["families"]["c2pa"]
    assert any(e["tag"] == "C2PA:Present" and e["value"] == "false" for e in result["families"]["c2pa"])


@pytest.mark.skipif(not FIXTURE.is_file(), reason="fixture C2PA ausente")
def test_c2pa_present_on_fixture():
    ok, _ = c2pa_runtime_status()
    if not ok:
        pytest.skip("c2pa-python nao instalado")
    result = extract_c2pa_manifest(str(FIXTURE))
    assert result["available"] is True
    assert result["present"] is True
    assert result["is_valid"] is True
    assert result["claim_generator"]
    assert result["actions"]
    assert any(a.get("action") == "c2pa.created" for a in result["actions"])
    assert result["store"]
    assert result["families"]["c2pa"]


@pytest.mark.skipif(not FIXTURE.is_file(), reason="fixture C2PA ausente")
def test_extract_image_metadata_includes_c2pa():
    ok, _ = c2pa_runtime_status()
    if not ok:
        pytest.skip("c2pa-python nao instalado")
    result = extract_image_metadata(str(FIXTURE))
    assert result["success"] is True
    assert result["summary"]["has_c2pa"] is True
    assert "c2pa-python" in (result["metadata"].get("engines") or [])
    assert result["c2pa_structured"]["present"] is True
    assert "c2pa" in result["metadata"]["families"]
    titles = [a["title"] for a in result["forensic_insights"]]
    assert any("C2PA" in t or "Content Credentials" in t for t in titles)


def test_forensic_insights_c2pa_invalid():
    alerts = build_forensic_insights(
        {},
        {},
        {},
        c2pa_structured={
            "available": True,
            "present": True,
            "is_valid": False,
            "validation_state": "Invalid",
            "claim_generator": "test",
            "validation_codes": ["claimSignature.mismatch"],
            "actions": [],
            "signature_info": {},
        },
    )
    assert any(a["severity"] == "high" and "validação falha" in a["title"] for a in alerts)
