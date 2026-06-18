"""Varredura da sequência ordenada de marcadores JPEG (SOI, APPn, DQT, SOF, SOS, EOI…)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

# ITU-T T.81 / ISO/IEC 10918-1
MARKER_NAMES: dict[int, str] = {
    0xC0: "SOF0",
    0xC1: "SOF1",
    0xC2: "SOF2",
    0xC3: "SOF3",
    0xC4: "DHT",
    0xC5: "SOF5",
    0xC6: "SOF6",
    0xC7: "SOF7",
    0xC8: "JPG",
    0xC9: "SOF9",
    0xCA: "SOF10",
    0xCB: "SOF11",
    0xCC: "DAC",
    0xCD: "SOF13",
    0xCE: "SOF14",
    0xCF: "SOF15",
    0xD0: "RST0",
    0xD1: "RST1",
    0xD2: "RST2",
    0xD3: "RST3",
    0xD4: "RST4",
    0xD5: "RST5",
    0xD6: "RST6",
    0xD7: "RST7",
    0xD8: "SOI",
    0xD9: "EOI",
    0xDA: "SOS",
    0xDB: "DQT",
    0xDD: "DRI",
    0xE0: "APP0",
    0xE1: "APP1",
    0xE2: "APP2",
    0xE3: "APP3",
    0xE4: "APP4",
    0xE5: "APP5",
    0xE6: "APP6",
    0xE7: "APP7",
    0xE8: "APP8",
    0xE9: "APP9",
    0xEA: "APP10",
    0xEB: "APP11",
    0xEC: "APP12",
    0xED: "APP13",
    0xEE: "APP14",
    0xEF: "APP15",
    0xFE: "COM",
}

KNOWN_MARKER_BYTES = frozenset(MARKER_NAMES.keys())


def _marker_name(code: int) -> str:
    return MARKER_NAMES.get(code, f"RESERVED_{code:02X}")


def _is_standalone_marker(code: int) -> bool:
    return code in (0xD8, 0xD9) or (0xD0 <= code <= 0xD7)


def _read_segment_length(data: bytes, pos: int) -> int | None:
    if pos + 2 > len(data):
        return None
    return int.from_bytes(data[pos : pos + 2], "big")


def _app_identifier(data: bytes, payload_start: int, payload_len: int) -> str | None:
    if payload_len < 2:
        return None
    end = min(payload_start + payload_len, len(data))
    chunk = data[payload_start:end]
    if len(chunk) >= 5 and chunk[0:5] == b"Exif\x00":
        return "Exif"
    if len(chunk) >= 5 and chunk[0:5] == b"JFIF\x00":
        return "JFIF"
    if len(chunk) >= 6 and chunk[0:6] == b"Adobe\x00":
        return "Adobe"
    if len(chunk) >= 5 and chunk[0:5] == b"XMP\x00":
        return "XMP"
    if len(chunk) >= 4:
        try:
            text = chunk[: min(16, len(chunk))].decode("ascii", errors="replace")
            cleaned = "".join(c if c.isprintable() else "." for c in text)
            return cleaned.strip() or None
        except Exception:
            return None
    return None


def _is_rst_marker_name(name: str) -> bool:
    return len(name) == 4 and name.startswith("RST") and name[3] in "01234567"


def _collapse_rst_markers(markers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Agrupa RST0–RST7 consecutivos em uma única entrada RST(N)."""
    collapsed: list[dict[str, Any]] = []
    i = 0
    while i < len(markers):
        m = markers[i]
        if _is_rst_marker_name(m.get("name", "")):
            first_offset = m["offset"]
            rst_count = 0
            while i < len(markers) and _is_rst_marker_name(markers[i].get("name", "")):
                rst_count += 1
                i += 1
            rst_label = f"RST({rst_count})"
            collapsed.append(
                {
                    "index": len(collapsed),
                    "offset": first_offset,
                    "code_hex": "FFD0–FFD7",
                    "name": rst_label,
                    "display_name": rst_label,
                    "segment_length": None,
                    "note": "marcadores de reinício (codificação DC diferencial / intervalo DRI)",
                    "rst_count": rst_count,
                }
            )
        else:
            entry = dict(m)
            entry["index"] = len(collapsed)
            collapsed.append(entry)
            i += 1
    return collapsed


def _skip_entropy_data(data: bytes, pos: int) -> int:
    """Avança após SOS até o próximo marcador 0xFF válido."""
    i = pos
    while i < len(data) - 1:
        if data[i] == 0xFF:
            nxt = data[i + 1]
            if nxt == 0x00:
                i += 2
                continue
            if nxt == 0xFF:
                i += 1
                continue
            if nxt in KNOWN_MARKER_BYTES:
                return i
        i += 1
    return len(data)


def scan_jpeg_marker_sequence(path: str) -> dict[str, Any]:
    """
    Lista marcadores JPEG na ordem do bitstream.

    Retorna offset, código (hex), nome, tamanho do segmento e identificador APP quando aplicável.
    """
    try:
        data = Path(path).read_bytes()
    except OSError as exc:
        return {"available": False, "reason": str(exc), "markers": []}

    if len(data) < 2 or data[0:2] != b"\xff\xd8":
        return {"available": False, "reason": "Arquivo não inicia com SOI (FFD8)", "markers": []}

    markers: list[dict[str, Any]] = []
    i = 0

    def append_marker(
        *,
        index: int,
        offset: int,
        code: int,
        segment_length: int | None,
        note: str | None = None,
        identifier: str | None = None,
    ) -> None:
        entry: dict[str, Any] = {
            "index": index,
            "offset": offset,
            "code_hex": f"FF{code:02X}",
            "name": _marker_name(code),
            "segment_length": segment_length,
        }
        if identifier:
            entry["identifier"] = identifier
        if note:
            entry["note"] = note
        markers.append(entry)

    append_marker(index=0, offset=0, code=0xD8, segment_length=2)
    i = 2
    in_scan = False
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
            append_marker(
                index=len(markers),
                offset=marker_offset,
                code=code,
                segment_length=2 if code in (0xD8, 0xD9) else None,
                note=None,
            )
            i += 1
            if code == 0xD9:
                break
            continue

        seg_len = _read_segment_length(data, i + 1)
        if seg_len is None or seg_len < 2:
            break

        payload_start = i + 3
        payload_len = seg_len - 2
        identifier = None
        if 0xE0 <= code <= 0xEF:
            identifier = _app_identifier(data, payload_start, payload_len)

        note = None
        if code == 0xDA:
            in_scan = True
            scan_index += 1
            note = f"início do scan #{scan_index} (dados entropia após o cabeçalho SOS)"

        append_marker(
            index=len(markers),
            offset=marker_offset,
            code=code,
            segment_length=seg_len,
            identifier=identifier,
            note=note,
        )

        i += 1 + seg_len

        if code == 0xDA:
            entropy_start = i
            next_pos = _skip_entropy_data(data, i)
            if next_pos > entropy_start:
                markers.append(
                    {
                        "index": len(markers),
                        "offset": entropy_start,
                        "code_hex": "—",
                        "name": "ENTROPY",
                        "segment_length": next_pos - entropy_start,
                        "note": "dados de imagem codificados (entre SOS e próximo marcador)",
                    }
                )
            i = next_pos
            in_scan = False

    markers = _collapse_rst_markers(markers)

    return {
        "available": True,
        "marker_count": len(markers),
        "markers": markers,
        "summary": _marker_sequence_summary(markers),
    }


def _marker_sequence_summary(markers: list[dict[str, Any]]) -> str:
    names: list[str] = []
    for m in markers:
        name = m.get("name", "?")
        if name == "ENTROPY":
            continue
        if name.startswith("APP") and m.get("identifier"):
            names.append(f"{name}({m['identifier']})")
        else:
            names.append(name)
    return " → ".join(names)
