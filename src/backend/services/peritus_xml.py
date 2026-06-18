"""Parser and validators for Peritus peritusCase.xml manifests."""

from __future__ import annotations

import base64
import hashlib
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any


PERITUS_XML_NAME = "peritusCase.xml"
UUID_BRACE_RE = re.compile(r"^\{([0-9a-fA-F-]{36})\}$")


def peritus_b64_sha256_to_hex(value: str) -> str:
    """Convert Peritus Base64 URL-safe SHA-256 digest to lowercase hex."""
    raw = value.strip()
    padded = raw + "=" * ((4 - len(raw) % 4) % 4)
    return base64.urlsafe_b64decode(padded).hex()


def sha256_hex_of_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalize_uuid(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    m = UUID_BRACE_RE.match(value)
    if m:
        return m.group(1).lower()
    return value.lower()


@dataclass
class PeritusFileRef:
    path: str
    hash_b64: str | None = None
    uuid: str | None = None
    kind: str = "file"


@dataclass
class PeritusCaseInfo:
    protocol_number: str
    title: str
    description: str | None = None
    inquiry_number: str | None = None
    process_number: str | None = None
    raw_fields: dict[str, str] = field(default_factory=dict)


@dataclass
class PeritusManifest:
    case_info: PeritusCaseInfo
    files: list[PeritusFileRef]
    evidence_count: int
    derived_count: int
    calculation_count: int
    media_count: int


def _text(el: ET.Element | None) -> str:
    return (el.text or "").strip() if el is not None else ""


def _parse_case_info(root: ET.Element) -> PeritusCaseInfo:
    info_el = root.find(".//peritusCaseInfo")
    fields: dict[str, str] = {}
    if info_el is not None:
        for child in info_el:
            field_id = child.attrib.get("id") or child.tag
            if child.tag == "input":
                if child.attrib.get("type") == "list":
                    selected = [
                        _text(item)
                        for item in child.findall("item")
                        if item.attrib.get("selected", "").lower() == "true"
                    ]
                    value = selected[0] if selected else ""
                else:
                    value = child.attrib.get("value", "")
                fields[field_id] = value.strip()
            else:
                fields[field_id] = _text(child)

    protocol = fields.get("PROCEDIMENTO") or "PERITUS-IMPORT"
    title = fields.get("EXAME") or protocol
    desc_parts = [
        f"{k}: {v}"
        for k, v in fields.items()
        if k not in ("PROCEDIMENTO", "EXAME") and v
    ]
    description = "\n".join(desc_parts) if desc_parts else None
    return PeritusCaseInfo(
        protocol_number=protocol[:50],
        title=title[:255],
        description=description,
        raw_fields=fields,
    )


def parse_peritus_manifest(xml_bytes: bytes) -> PeritusManifest:
    """Parse peritusCase.xml into structured manifest."""
    root = ET.fromstring(xml_bytes)
    case_info = _parse_case_info(root)

    files: list[PeritusFileRef] = []
    seen_paths: set[str] = set()

    def add_path(path: str, hash_b64: str | None = None, uuid_val: str | None = None, kind: str = "file"):
        norm = path.replace("\\", "/").lstrip("/")
        if not norm or norm in seen_paths:
            return
        seen_paths.add(norm)
        files.append(
            PeritusFileRef(
                path=norm,
                hash_b64=hash_b64,
                uuid=normalize_uuid(uuid_val),
                kind=kind,
            )
        )

    for tag, kind in (("evidence", "evidence"), ("derivedEvidence", "derived")):
        for el in root.findall(f".//{tag}"):
            add_path(
                _text(el.find("path")),
                _text(el.find("hash")) or el.findtext("hash"),
                _text(el.find("uuid")),
                kind,
            )

    for media in root.findall(".//media"):
        for file_el in media.findall(".//files/file"):
            rel = _text(file_el.find("relativepath"))
            if not rel:
                continue
            designation = _text(media.find("designation"))
            full = f"{designation}/{rel}" if designation else rel
            hash_el = file_el.find("hash")
            hash_b64 = hash_el.text.strip() if hash_el is not None and hash_el.text else None
            add_path(full, hash_b64, _text(file_el.find("uuid")), "media_file")

    evidence_count = len(root.findall(".//evidence"))
    derived_count = len(root.findall(".//derivedEvidence"))
    calculation_count = len(root.findall(".//calculation"))
    media_count = len(root.findall(".//media"))

    return PeritusManifest(
        case_info=case_info,
        files=files,
        evidence_count=evidence_count,
        derived_count=derived_count,
        calculation_count=calculation_count,
        media_count=media_count,
    )


def list_zip_member_paths(zip_names: list[str]) -> list[str]:
    return sorted(
        n.replace("\\", "/")
        for n in zip_names
        if n and not n.endswith("/") and PurePosixPath(n).name != PERITUS_XML_NAME
    )


def validate_peritus_zip_members(
    zip_names: list[str],
    xml_bytes: bytes,
    file_reader: Any,
) -> dict[str, Any]:
    """
    Validate Peritus ZIP against XML paths and hashes.
    file_reader: callable(path) -> bytes
    """
    issues: list[str] = []
    manifest = parse_peritus_manifest(xml_bytes)
    xml_paths = {f.path for f in manifest.files}
    zip_paths = set(list_zip_member_paths(zip_names))

    missing_in_zip = sorted(xml_paths - zip_paths)
    orphan_in_zip = sorted(zip_paths - xml_paths)

    if missing_in_zip:
        issues.append(f"{len(missing_in_zip)} arquivo(s) referenciado(s) no XML ausente(s) no ZIP")
    # Arquivos extras no ZIP (gerenciador Peritus) sao permitidos — nao invalidam o pacote.

    hash_mismatch: list[dict[str, str]] = []
    checked = 0
    for ref in manifest.files:
        if ref.path not in zip_paths:
            continue
        if not ref.hash_b64:
            continue
        data = file_reader(ref.path)
        actual_hex = sha256_hex_of_bytes(data)
        expected_hex = peritus_b64_sha256_to_hex(ref.hash_b64)
        checked += 1
        if actual_hex != expected_hex:
            hash_mismatch.append(
                {
                    "path": ref.path,
                    "expected_hex": expected_hex,
                    "actual_hex": actual_hex,
                }
            )

    if hash_mismatch:
        issues.append(f"{len(hash_mismatch)} arquivo(s) com hash divergente")

    return {
        "valid": not issues,
        "issues": issues,
        "manifest": manifest,
        "files_checked": checked,
        "missing_in_zip": missing_in_zip[:20],
        "orphan_in_zip": orphan_in_zip[:20],
        "orphan_count": len(orphan_in_zip),
        "hash_mismatch": hash_mismatch[:20],
        "evidence_count": manifest.evidence_count,
        "derived_count": manifest.derived_count,
        "calculation_count": manifest.calculation_count,
    }
