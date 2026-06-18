"""Extracao unificada de metadados de imagem para o plugin metadata."""

from __future__ import annotations

import re
import shutil
import struct
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image
from PIL.ExifTags import TAGS

from core.metadata.adobe_property_hints import adobe_property_hint
from core.metadata.exif_property_hints import exif_property_hint
from core.metadata.forensic_metadata_insights import build_forensic_insights
from core.metadata.icc_property_hints import icc_property_hint
from core.metadata.jpeg_structure import read_jpeg_structure
from core.metadata.makernote_property_hints import makernote_property_hint
from core.metadata.xmp_packet import extract_xmp_packet

_TAG_HINT_RESOLVERS = {
    "exif": exif_property_hint,
    "adobe": adobe_property_hint,
    "icc": icc_property_hint,
    "makernotes": makernote_property_hint,
}

# Prefixos ExifTool / grupos para MakerNotes conhecidos
MAKERNOTE_PREFIXES = (
    "MakerNotes",
    "Canon",
    "Nikon",
    "Sony",
    "Fujifilm",
    "FujiFilm",
    "Olympus",
    "Pentax",
    "Panasonic",
    "Leica",
    "Apple",
    "DJI",
    "GoPro",
    "Sigma",
    "Minolta",
    "Kodak",
    "Reconyx",
    "GE",
    "Samsung",
)

ADOBE_TAG_HINTS = (
    "adobe",
    "photoshop",
    "dng",
    "crs",
    "lightroom",
    "flag",
    "modifier",
    "xmptoolkit",
)


def _safe_str(value: Any, max_len: int = 4096) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        try:
            text = value.decode("utf-8", errors="replace")
        except Exception:
            text = repr(value[:200])
    else:
        text = str(value)
    if len(text) > max_len:
        return text[: max_len - 3] + "..."
    return text


def _classify_tag_group(tag: str) -> str:
    if ":" in tag:
        prefix = tag.split(":", 1)[0]
        if prefix == "EXIF":
            return "exif"
        if prefix == "IPTC":
            return "iptc"
        if prefix == "XMP":
            return "xmp"
        if prefix.startswith("ICC"):
            return "icc"
        if prefix in MAKERNOTE_PREFIXES or prefix == "MakerNotes":
            return "makernotes"
        prefix_l = prefix.lower()
        if any(h in prefix_l for h in ADOBE_TAG_HINTS) or prefix in ("Photoshop", "Adobe", "DNG", "CRS"):
            return "adobe"
        if prefix in ("JFIF", "Composite", "File", "QuickTime", "Trailer"):
            return "other"
        return "other"
    tag_l = tag.lower()
    if tag.startswith("GPS") or "gps" in tag_l:
        return "exif"
    if any(h in tag_l for h in ADOBE_TAG_HINTS):
        return "adobe"
    return "exif"


def _tag_entry(tag: str, value: Any, source: str) -> dict[str, str]:
    group = _classify_tag_group(tag)
    entry: dict[str, str] = {
        "tag": tag,
        "value": _safe_str(value),
        "group": group,
        "source": source,
    }
    resolver = _TAG_HINT_RESOLVERS.get(group)
    if resolver:
        hint = resolver(tag)
        if hint:
            entry["hint"] = hint
    return entry


def _exiftool_available() -> bool:
    return shutil.which("exiftool") is not None or shutil.which("exiftool.exe") is not None


def _read_exiftool(path: str) -> dict[str, Any]:
    import exiftool

    families: dict[str, list[dict[str, str]]] = {
        "exif": [],
        "iptc": [],
        "xmp": [],
        "icc": [],
        "makernotes": [],
        "adobe": [],
        "other": [],
    }
    warnings: list[str] = []

    with exiftool.ExifToolHelper() as et:
        # PyExifTool >= 0.5.x: get_tags(files, tags) — tags=None retorna todas as tags
        tags = et.get_metadata(path)

    for block in tags:
        for tag, value in block.items():
            if tag in ("SourceFile", "ExifTool:ExifToolVersion"):
                continue
            entry = _tag_entry(tag, value, "exiftool")
            group = entry["group"]
            if group not in families:
                group = "other"
            families[group].append(entry)

    for key in families:
        families[key].sort(key=lambda e: e["tag"].lower())

    return {
        "engine": "exiftool",
        "engines": ["exiftool"],
        "available": True,
        "families": families,
        "warnings": warnings,
    }


def _read_pillow_exif(path: str) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    with Image.open(path) as img:
        exif = img.getexif()
        if not exif:
            return entries
        for tag_id, value in exif.items():
            name = TAGS.get(tag_id, str(tag_id))
            entries.append(_tag_entry(name, value, "pillow"))
    return entries


def _read_xmp_from_bytes(data: bytes) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for match in re.finditer(rb"<xmp:[^>]+>([^<]*)</xmp:[^>]+>", data):
        try:
            tag = match.group(0).decode("utf-8", errors="replace")[:120]
            val = match.group(1).decode("utf-8", errors="replace")
            entries.append(_tag_entry(f"XMP:{tag[:60]}", val, "xmp_sniff"))
        except Exception:
            continue
    if b"xmp:CreatorTool" in data or b"photoshop:" in data.lower():
        entries.append(
            _tag_entry("XMP:PacketDetected", "Sim (segmento XMP encontrado no arquivo)", "xmp_sniff")
        )
    return entries[:200]


def _parse_icc_profile(icc_bytes: bytes) -> dict[str, Any]:
    if len(icc_bytes) < 128:
        return {"available": False, "reason": "Perfil ICC muito curto"}
    try:
        profile_size = struct.unpack(">I", icc_bytes[0:4])[0]
        cmm = icc_bytes[4:8].decode("latin-1", errors="replace").strip()
        version = icc_bytes[8:12].hex()
        device_class = icc_bytes[12:16].decode("latin-1", errors="replace").strip()
        color_space = icc_bytes[16:20].decode("latin-1", errors="replace").strip()
        pcs = icc_bytes[20:24].decode("latin-1", errors="replace").strip()
        desc = ""
        tag_count = struct.unpack(">I", icc_bytes[128:132])[0] if len(icc_bytes) >= 132 else 0
        return {
            "available": True,
            "size_bytes": profile_size,
            "cmm_type": cmm,
            "version_hex": version,
            "device_class": device_class,
            "color_space": color_space,
            "profile_connection_space": pcs,
            "tag_count": tag_count,
            "source": "icc_binary_header",
        }
    except Exception as exc:
        return {"available": False, "reason": str(exc)}


def _read_icc(path: str) -> dict[str, Any]:
    icc_entries: list[dict[str, str]] = []
    profile_info: dict[str, Any] = {"available": False}

    try:
        with Image.open(path) as img:
            icc_bytes = img.info.get("icc_profile")
            if icc_bytes:
                profile_info = _parse_icc_profile(icc_bytes if isinstance(icc_bytes, bytes) else bytes(icc_bytes))
                profile_info["embedded_in_file"] = True
    except Exception as exc:
        profile_info = {"available": False, "reason": str(exc)}

    return {"profile": profile_info, "tags": icc_entries}


def _empty_families() -> dict[str, list[dict[str, str]]]:
    return {
        "exif": [],
        "iptc": [],
        "xmp": [],
        "icc": [],
        "makernotes": [],
        "adobe": [],
        "other": [],
    }


def _normalize_tag_for_dedup(tag: str) -> str:
    """Chave de deduplicação: nome local sem prefixo EXIF:/GPS:."""
    if ":" in tag:
        prefix, local = tag.split(":", 1)
        if prefix.upper() in ("EXIF", "GPS", "IFD0", "IFD1"):
            return local.lower()
    return tag.lower()


def _dedupe_family_entries(entries: list[dict[str, str]]) -> list[dict[str, str]]:
    """Funde entradas com mesma tag normalizada e mesmo valor, unindo fontes."""
    merged: dict[tuple[str, str], dict[str, str]] = {}
    order: list[tuple[str, str]] = []
    for entry in entries:
        key = (_normalize_tag_for_dedup(entry["tag"]), entry["value"])
        if key in merged:
            existing = merged[key]
            src = existing.get("source", "")
            new_src = entry.get("source", "")
            if new_src and new_src not in src.split("+"):
                existing["source"] = f"{src}+{new_src}" if src else new_src
            if not existing.get("hint") and entry.get("hint"):
                existing["hint"] = entry["hint"]
            continue
        merged[key] = dict(entry)
        order.append(key)
    return [merged[k] for k in order]


def _merge_families(
    base: dict[str, list[dict[str, str]]],
    extra: dict[str, list[dict[str, str]]],
) -> None:
    """Append entries from extra into base, skipping exact duplicates."""
    for family, entries in extra.items():
        if family not in base:
            base[family] = []
        seen = {(e["tag"], e["value"], e.get("source", "")) for e in base[family]}
        for entry in entries:
            key = (entry["tag"], entry["value"], entry.get("source", ""))
            if key in seen:
                continue
            base[family].append(entry)
            seen.add(key)
    for family in base:
        base[family] = _dedupe_family_entries(base[family])
        base[family].sort(key=lambda e: (e["tag"].lower(), e.get("source", "")))


def _read_supplementary(path: str) -> dict[str, Any]:
    """Motores complementares: Pillow EXIF, sniff XMP e resumo ICC embutido."""
    families = _empty_families()
    families["exif"] = _read_pillow_exif(path)

    try:
        raw = Path(path).read_bytes()
        if len(raw) > 50:
            families["xmp"] = _read_xmp_from_bytes(raw)
    except OSError:
        pass

    icc_data = _read_icc(path)
    if icc_data["profile"].get("available"):
        p = icc_data["profile"]
        families["icc"].append(
            _tag_entry(
                "ICC:ProfileSummary",
                f"{p.get('device_class')} / {p.get('color_space')} ({p.get('size_bytes')} bytes)",
                "pillow_icc",
            )
        )

    for entry in list(families["exif"]):
        tag_lower = entry["tag"].lower()
        if "maker" in tag_lower or tag_lower == "makernote":
            families["makernotes"].append(entry)
        if any(h in tag_lower for h in ADOBE_TAG_HINTS):
            families["adobe"].append(entry)

    return {
        "engine": "supplementary",
        "engines": ["pillow", "xmp_sniff", "pillow_icc"],
        "available": True,
        "families": families,
        "warnings": [],
    }


def _read_combined_metadata(path: str) -> dict[str, Any]:
    """Executa ExifTool (se disponivel) e sempre os motores complementares."""
    families = _empty_families()
    warnings: list[str] = []
    engines: list[str] = []

    if _exiftool_available():
        try:
            exif_meta = _read_exiftool(path)
            _merge_families(families, exif_meta["families"])
            engines.append("exiftool")
        except Exception as exc:
            warnings.append(f"ExifTool falhou ({exc}).")
    else:
        warnings.append(
            "ExifTool nao encontrado no PATH — IPTC completo, MakerNotes decodificados "
            "e XMP estruturado dependem da instalacao do binario exiftool."
        )

    supp = _read_supplementary(path)
    _merge_families(families, supp["families"])
    engines.extend(supp["engines"])

    engine_label = "+".join(engines) if engines else "none"

    return {
        "engine": engine_label,
        "engines": engines,
        "available": True,
        "families": families,
        "warnings": warnings,
    }


def _build_summary(file_info: dict[str, Any], meta: dict[str, Any], jpeg: dict[str, Any]) -> dict[str, Any]:
    families = meta.get("families", {})
    counts = {k: len(families.get(k, [])) for k in ("exif", "iptc", "xmp", "icc", "makernotes", "adobe", "other")}
    has_gps = any("gps" in e.get("tag", "").lower() for e in families.get("exif", []) + families.get("other", []))
    icc_ok = bool(families.get("icc")) or meta.get("icc_profile", {}).get("available")

    return {
        "format": file_info.get("format"),
        "width": file_info.get("width"),
        "height": file_info.get("height"),
        "is_jpeg": file_info.get("is_jpeg"),
        "metadata_engine": meta.get("engine"),
        "metadata_engines": meta.get("engines", []),
        "tag_counts": counts,
        "has_gps": has_gps,
        "has_icc": icc_ok,
        "has_makernotes": counts.get("makernotes", 0) > 0,
        "has_adobe_tags": counts.get("adobe", 0) > 0,
        "jpeg_structure_available": jpeg.get("available", False),
        "quantization_table_count": len(jpeg.get("quantization_tables", [])),
        "huffman_dc_count": len(jpeg.get("huffman_dc_tables", [])),
        "huffman_ac_count": len(jpeg.get("huffman_ac_tables", [])),
    }


def _forensic_highlights(families: dict[str, list[dict[str, str]]]) -> list[dict[str, str]]:
    """Campos frequentes em laudo — busca em todas as familias."""
    keys_of_interest = (
        "model",
        "make",
        "software",
        "datetime",
        "date",
        "gps",
        "lens",
        "orientation",
        "artist",
        "copyright",
        "creator",
        "document",
        "history",
        "flash",
        "iso",
        "shuttercount",
        "serial",
    )
    highlights: list[dict[str, str]] = []
    seen: set[str] = set()
    source_rank = {"exiftool": 0, "pillow": 1, "pillow_icc": 2, "xmp_sniff": 3}
    candidates: list[tuple[int, dict[str, str]]] = []
    for group, entries in families.items():
        for entry in entries:
            tag_l = entry["tag"].lower()
            norm = _normalize_tag_for_dedup(entry["tag"])
            if any(k in tag_l for k in keys_of_interest) and norm not in seen:
                seen.add(norm)
                rank = source_rank.get(entry.get("source", "").split("+")[0], 9)
                candidates.append((rank, {**entry, "family": group}))
    candidates.sort(key=lambda x: (x[0], x[1]["tag"].lower()))
    highlights = [e for _, e in candidates]
    return highlights[:40]


def extract_image_metadata(path: str) -> dict[str, Any]:
    """Extrai metadados completos + estrutura JPEG para uma imagem."""
    p = Path(path)
    if not p.is_file():
        return {"success": False, "error": f"Arquivo nao encontrado: {path}"}

    file_info: dict[str, Any] = {
        "filename": p.name,
        "suffix": p.suffix.lower(),
        "size_bytes": p.stat().st_size,
        "is_jpeg": p.suffix.lower() in (".jpg", ".jpeg"),
    }

    try:
        with Image.open(path) as img:
            file_info.update(
                {
                    "format": img.format,
                    "mode": img.mode,
                    "width": img.width,
                    "height": img.height,
                }
            )
    except Exception as exc:
        return {"success": False, "error": f"Falha ao abrir imagem: {exc}"}

    meta = _read_combined_metadata(path)

    icc_profile = _read_icc(path)
    meta["icc_profile"] = icc_profile.get("profile", {})

    xmp_structured = extract_xmp_packet(path)
    meta["xmp_structured"] = xmp_structured

    jpeg_structure = read_jpeg_structure(path)
    families = meta.get("families", {})
    summary = _build_summary(file_info, meta, jpeg_structure)
    highlights = _forensic_highlights(families)
    if xmp_structured.get("available"):
        summary["has_xmp_packet"] = True
        summary["xmp_property_count"] = xmp_structured.get("property_count", 0)
        summary["xmp_packet_sha256"] = xmp_structured.get("packet_sha256")
    else:
        summary["has_xmp_packet"] = False
        summary["xmp_property_count"] = 0

    forensic_insights = build_forensic_insights(families, xmp_structured, summary)

    return {
        "success": True,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "file": file_info,
        "summary": summary,
        "highlights": highlights,
        "forensic_insights": forensic_insights,
        "metadata": meta,
        "jpeg_structure": jpeg_structure,
        "xmp_structured": xmp_structured,
    }
