"""Metadados de arquivos Peritus — tipo, MIME e indice do XML."""

from __future__ import annotations

import mimetypes
import xml.etree.ElementTree as ET
from pathlib import Path

from services.peritus_xml import PERITUS_XML_NAME, normalize_uuid, peritus_b64_sha256_to_hex

MIME_TYPE_MAP = {
    "image/jpeg": "imagem",
    "image/png": "imagem",
    "image/tiff": "imagem",
    "image/bmp": "imagem",
    "image/webp": "imagem",
    "image/gif": "imagem",
    "audio/mpeg": "audio",
    "audio/mp3": "audio",
    "audio/wav": "audio",
    "audio/x-wav": "audio",
    "audio/ogg": "audio",
    "audio/opus": "audio",
    "video/mp4": "video",
    "video/avi": "video",
    "video/x-msvideo": "video",
    "video/mpeg": "video",
    "video/quicktime": "video",
    "application/pdf": "pdf",
    "text/xml": "xml",
    "application/xml": "xml",
}


def infer_file_type(filename: str, mime_type: str | None = None) -> str:
    if mime_type:
        mapped = MIME_TYPE_MAP.get(mime_type.lower())
        if mapped:
            return mapped
    ext = Path(filename).suffix.lower()
    if ext in (".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp", ".webp", ".gif"):
        return "imagem"
    if ext in (".mp3", ".wav", ".ogg", ".opus", ".oga", ".m4a", ".aac"):
        return "audio"
    if ext in (".mp4", ".avi", ".mpeg", ".mpg", ".mov", ".mkv", ".webm"):
        return "video"
    if ext == ".pdf":
        return "pdf"
    if ext in (".xml",):
        return "xml"
    return "outros"


def guess_mime(filename: str) -> str | None:
    guessed, _ = mimetypes.guess_type(filename)
    return guessed


def peritus_folder_label(relative_path: str) -> str:
    """Pasta-bloco Peritus: raiz ou caminho do diretorio pai."""
    norm = relative_path.replace("\\", "/").lstrip("/")
    if "/" not in norm:
        return "(raiz)"
    return norm.rsplit("/", 1)[0]


def _text(el: ET.Element | None) -> str:
    return (el.text or "").strip() if el is not None else ""


def build_xml_path_index(xml_bytes: bytes) -> dict[str, dict]:
    """Mapa path relativo -> metadados do peritusCase.xml."""
    root = ET.fromstring(xml_bytes)
    index: dict[str, dict] = {}

    def add(path: str, **meta: object) -> None:
        norm = path.replace("\\", "/").lstrip("/")
        if not norm:
            return
        entry = index.setdefault(norm, {})
        entry.update({k: v for k, v in meta.items() if v is not None})

    for tag, kind in (("evidence", "evidence"), ("derivedEvidence", "derived")):
        for el in root.findall(f".//{tag}"):
            path = _text(el.find("path"))
            if not path:
                continue
            hash_el = el.find("hash")
            hash_b64 = hash_el.text.strip() if hash_el is not None and hash_el.text else None
            sha256_hex = None
            if hash_b64:
                try:
                    sha256_hex = peritus_b64_sha256_to_hex(hash_b64)
                except Exception:
                    sha256_hex = None
            mime = _text(el.find("mimeType")) or None
            add(
                path,
                peritus_uuid=normalize_uuid(_text(el.find("uuid"))),
                sha256=sha256_hex,
                mime_type=mime,
                kind=kind,
                is_derived=kind == "derived",
            )

    for media in root.findall(".//media"):
        designation = _text(media.find("designation"))
        for file_el in media.findall(".//files/file"):
            rel = _text(file_el.find("relativepath"))
            if not rel:
                continue
            full = f"{designation}/{rel}" if designation else rel
            hash_el = file_el.find("hash")
            hash_b64 = hash_el.text.strip() if hash_el is not None and hash_el.text else None
            sha256_hex = None
            if hash_b64:
                try:
                    sha256_hex = peritus_b64_sha256_to_hex(hash_b64)
                except Exception:
                    sha256_hex = None
            add(
                full,
                peritus_uuid=normalize_uuid(_text(file_el.find("uuid"))),
                sha256=sha256_hex,
                kind="media_file",
            )

    return index


def folder_sort_key(label: str) -> tuple:
    if label == "(raiz)":
        return (0, "")
    if label == "derived-files":
        return (1, label)
    return (2, label.lower())
