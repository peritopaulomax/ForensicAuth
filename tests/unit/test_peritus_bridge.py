"""Tests for Peritus case package import/export bridge."""

from __future__ import annotations

import hashlib
import json
import uuid
import zipfile
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from models.custody_record import CustodyRecord
from services.peritus_bridge_service import PeritusBridgeService
from services.peritus_xml import (
    PERITUS_XML_NAME,
    parse_peritus_manifest,
    peritus_b64_sha256_to_hex,
    validate_peritus_zip_members,
)

IMAGEM9_ZIP = Path(__file__).resolve().parents[2] / "Imagem9.zip"


def test_peritus_b64_to_hex_known_sample():
    hex_val = peritus_b64_sha256_to_hex("HB_bg93_4lk4qUfiLozGWiGikXKY56ZCust-adx-4-w")
    assert len(hex_val) == 64
    assert all(c in "0123456789abcdef" for c in hex_val)


@pytest.mark.skipif(not IMAGEM9_ZIP.is_file(), reason="Imagem9.zip not in project root")
def test_validate_imagem9_zip():
    with zipfile.ZipFile(IMAGEM9_ZIP, "r") as zf:
        names = zf.namelist()
        xml = zf.read(PERITUS_XML_NAME)
        report = validate_peritus_zip_members(
            names,
            xml,
            lambda p: zf.read(p),
        )
    assert report["valid"], report["issues"]
    assert report["evidence_count"] == 4
    assert report["derived_count"] == 28
    assert report["calculation_count"] == 28
    assert report["files_checked"] >= 4


@pytest.mark.skipif(not IMAGEM9_ZIP.is_file(), reason="Imagem9.zip not in project root")
def test_parse_imagem9_case_info():
    with zipfile.ZipFile(IMAGEM9_ZIP, "r") as zf:
        manifest = parse_peritus_manifest(zf.read(PERITUS_XML_NAME))
    assert "123456" in manifest.case_info.protocol_number or manifest.case_info.protocol_number
    assert manifest.case_info.title


@pytest.mark.skipif(not IMAGEM9_ZIP.is_file(), reason="Imagem9.zip not in project root")
def test_peritus_import_export_bit_identical(db_session: Session, test_user, tmp_path):
    """Round-trip: export must match original ZIP bytes when unmodified."""
    svc = PeritusBridgeService(db_session)
    report = svc.validate_package(IMAGEM9_ZIP, db=db_session)
    assert report["valid"], report.get("issues")

    original_sha = hashlib.sha256(IMAGEM9_ZIP.read_bytes()).hexdigest()

    result = svc.import_case(IMAGEM9_ZIP, test_user, skip_conflict_check=True)
    case_id = uuid.UUID(result["case_id"])

    export_path = tmp_path / "exported.zip"
    svc.export_case(case_id, test_user, export_path)

    exported_sha = hashlib.sha256(export_path.read_bytes()).hexdigest()
    assert exported_sha == original_sha

    binding = json.loads(
        (Path(svc.settings.PERITUS_CASES_DIR) / str(case_id) / "binding.json").read_text()
    )
    assert binding.get("modified") is False

    file_records = (
        db_session.query(CustodyRecord)
        .filter(
            CustodyRecord.case_id == case_id,
            CustodyRecord.record_type == "peritus_file_imported",
        )
        .count()
    )
    assert file_records == result.get("custody_files_registered", 0)
    assert file_records > 0

    svc.remove_case_storage(case_id)
