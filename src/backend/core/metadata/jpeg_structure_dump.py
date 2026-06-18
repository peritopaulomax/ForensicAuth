"""Dump forense da estrutura JPEG: marcadores ordenados, DQT/DHT e thumbnails embutidos."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.metadata.jpeg_markers import (
    KNOWN_MARKER_BYTES,
    MARKER_NAMES,
    _app_identifier,
    _collapse_rst_markers,
    _is_rst_marker_name,
    _is_standalone_marker,
    _marker_name,
    _read_segment_length,
    _skip_entropy_data,
)

JPEG_EXTENSIONS = frozenset({".jpg", ".jpeg", ".jfif"})


def is_jpeg_file(path: str) -> bool:
    """True se extensão conhecida ou magic bytes SOI (FFD8)."""
    suffix = Path(path).suffix.lower()
    if suffix in JPEG_EXTENSIONS:
        return True
    try:
        with open(path, "rb") as fh:
            return fh.read(2) == b"\xff\xd8"
    except OSError:
        return False


def parse_dqt_payload(payload: bytes) -> list[dict[str, Any]]:
    tables: list[dict[str, Any]] = []
    i = 0
    while i < len(payload):
        pq = payload[i]
        i += 1
        precision = (pq >> 4) & 0x0F
        table_id = pq & 0x0F
        if precision == 0:
            matrix = list(payload[i : i + 64])
            i += 64
        else:
            matrix = []
            for _ in range(64):
                if i + 2 > len(payload):
                    break
                matrix.append(int.from_bytes(payload[i : i + 2], "big"))
                i += 2
        tables.append(
            {
                "table_id": int(table_id),
                "precision": int(precision),
                "matrix": matrix,
            }
        )
    return tables


def parse_dht_payload(payload: bytes) -> list[dict[str, Any]]:
    tables: list[dict[str, Any]] = []
    i = 0
    while i < len(payload):
        tc = payload[i]
        i += 1
        table_class = (tc >> 4) & 0x0F
        table_id = tc & 0x0F
        counts = list(payload[i : i + 16])
        i += 16
        total = sum(counts)
        values = list(payload[i : i + total])
        i += total
        tables.append(
            {
                "table_class": int(table_class),
                "table_id": int(table_id),
                "counts": counts,
                "values": values,
            }
        )
    return tables


def _marker_display_name(name: str, identifier: str | None = None) -> str:
    if name.startswith("APP") and identifier:
        return f"{name}({identifier})"
    return name


def _marker_label(marker: dict[str, Any]) -> str:
    """Rótulo seguro para UI/resumo (nunca KeyError em marcadores colapsados)."""
    display = marker.get("display_name")
    if isinstance(display, str) and display:
        return display
    name = marker.get("name") or "?"
    if name.startswith("APP") and marker.get("identifier"):
        return f"{name}({marker['identifier']})"
    return str(name)


def _is_valid_thumbnail_structure(markers: list[dict[str, Any]]) -> bool:
    """Thumbnail válido: SOI + (APP|DQT|SOF|DHT)* + SOS + EOI."""
    if not markers:
        return False
    names = [m["name"] for m in markers if m["name"] != "ENTROPY"]
    if names[0] != "SOI" or names[-1] != "EOI":
        return False
    if "SOS" not in names:
        return False
    sos_idx = names.index("SOS")
    pre_sos = names[1:sos_idx]
    required_pre = {"APP0", "APP1", "APP2", "APP3", "APP4", "APP5", "APP6", "APP7",
                    "APP8", "APP9", "APP10", "APP11", "APP12", "APP13", "APP14", "APP15",
                    "DQT", "SOF0", "SOF1", "SOF2", "DHT"}
    if not any(n in required_pre or n.startswith("SOF") or n.startswith("APP") for n in pre_sos):
        return False
    return True


def _scan_markers_from_bytes(
    data: bytes,
    *,
    base_offset: int = 0,
    include_entropy: bool = True,
) -> list[dict[str, Any]]:
    """Varre marcadores em um buffer (arquivo ou thumbnail embutido)."""
    if len(data) < 2 or data[0:2] != b"\xff\xd8":
        return []

    markers: list[dict[str, Any]] = []
    i = 2

    def append_marker(
        *,
        offset: int,
        code: int,
        segment_length: int | None,
        payload: bytes | None = None,
        identifier: str | None = None,
        note: str | None = None,
    ) -> None:
        name = _marker_name(code)
        entry: dict[str, Any] = {
            "index": len(markers),
            "offset": base_offset + offset,
            "code_hex": f"FF{code:02X}",
            "name": name,
            "display_name": _marker_display_name(name, identifier),
            "segment_length": segment_length,
        }
        if identifier:
            entry["identifier"] = identifier
        if note:
            entry["note"] = note

        if name == "DQT" and payload is not None:
            entry["dqt_tables"] = parse_dqt_payload(payload)
        if name == "DHT" and payload is not None:
            entry["dht_tables"] = parse_dht_payload(payload)
        if name.startswith("APP") and payload is not None:
            thumb = extract_thumbnail_from_app_payload(payload, base_offset=base_offset + offset)
            if thumb:
                entry["has_thumbnail"] = True
                entry["thumbnail"] = thumb
            else:
                entry["has_thumbnail"] = False

        markers.append(entry)

    append_marker(offset=0, code=0xD8, segment_length=2)

    scan_index = 0
    while i < len(data):
        if data[i] != 0xFF:
            i += 1
            continue

        marker_offset = i
        while i < len(data) and data[i] == 0xFF:
            i += 1
        if i >= len(data):
            break

        code = data[i]
        if code == 0x00:
            i += 1
            continue

        if _is_standalone_marker(code):
            append_marker(offset=marker_offset, code=code, segment_length=2 if code in (0xD8, 0xD9) else None)
            i += 1
            if code == 0xD9:
                break
            continue

        seg_len = _read_segment_length(data, i + 1)
        if seg_len is None or seg_len < 2:
            break

        payload_start = i + 3
        payload_len = seg_len - 2
        payload = data[payload_start : payload_start + payload_len]
        identifier = None
        if 0xE0 <= code <= 0xEF:
            identifier = _app_identifier(data, payload_start, payload_len)

        note = None
        if code == 0xDA:
            scan_index += 1
            note = f"início do scan #{scan_index}"

        append_marker(
            offset=marker_offset,
            code=code,
            segment_length=seg_len,
            payload=payload,
            identifier=identifier,
            note=note,
        )

        i += 1 + seg_len

        if code == 0xDA and include_entropy:
            entropy_start = i
            next_pos = _skip_entropy_data(data, i)
            if next_pos > entropy_start:
                markers.append(
                    {
                        "index": len(markers),
                        "offset": base_offset + entropy_start,
                        "code_hex": "—",
                        "name": "ENTROPY",
                        "display_name": "ENTROPY",
                        "segment_length": next_pos - entropy_start,
                        "note": "dados de imagem codificados",
                    }
                )
            i = next_pos

    return _collapse_rst_markers(markers)


def extract_thumbnail_from_app_payload(
    payload: bytes,
    *,
    base_offset: int = 0,
) -> dict[str, Any] | None:
    """Detecta e extrai estrutura de thumbnail JPEG embutido em segmento APP."""
    candidates: list[int] = []
    pos = 0
    while pos < len(payload) - 1:
        if payload[pos : pos + 2] == b"\xff\xd8":
            candidates.append(pos)
        pos += 1

    for soi_pos in candidates:
        sub = payload[soi_pos:]
        markers = _scan_markers_from_bytes(sub, base_offset=base_offset + soi_pos, include_entropy=False)
        filtered = [m for m in markers if m["name"] != "ENTROPY"]
        if _is_valid_thumbnail_structure(filtered):
            return {
                "offset_in_app": soi_pos,
                "available": True,
                "marker_count": len(filtered),
                "markers": filtered,
                "summary": " → ".join(_marker_label(m) for m in filtered),
            }
    return None


def dump_jpeg_structure(path: str) -> dict[str, Any]:
    """Extrai dump completo da estrutura JPEG de um arquivo."""
    if not is_jpeg_file(path):
        return {"available": False, "reason": "Arquivo não é JPEG", "markers": []}

    try:
        data = Path(path).read_bytes()
    except OSError as exc:
        return {"available": False, "reason": str(exc), "markers": []}

    if len(data) < 2 or data[0:2] != b"\xff\xd8":
        return {"available": False, "reason": "Arquivo não inicia com SOI (FFD8)", "markers": []}

    markers = _scan_markers_from_bytes(data, include_entropy=True)
    comparison_markers = [m for m in markers if m["name"] != "ENTROPY"]

    return {
        "available": True,
        "path": path,
        "filename": Path(path).name,
        "marker_count": len(markers),
        "comparison_marker_count": len(comparison_markers),
        "markers": markers,
        "comparison_markers": comparison_markers,
        "summary": " → ".join(
            _marker_label(m) + ("+" if m.get("has_thumbnail") else "")
            for m in comparison_markers
        ),
    }
