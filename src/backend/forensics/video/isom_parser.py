"""Parser ISO BMFF (MP4/MOV/M4V) com grafo, arvore e metadados forenses."""

from __future__ import annotations

import json
import os
import struct
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import networkx as nx
from networkx.readwrite import json_graph

ProgressFn = Optional[Callable[[int, str], None]]

BOX_DESCRIPTIONS: Dict[str, str] = {
    "ftyp": "File Type Box - tipo e compatibilidade",
    "moov": "Movie Box - metadados globais do container",
    "mvhd": "Movie Header Box - timescale e duracao do filme",
    "trak": "Track Box - trilha de audio/video/metadados",
    "tkhd": "Track Header Box - identificador e duracao da trilha",
    "mdia": "Media Box - dados da midia da trilha",
    "mdhd": "Media Header Box - timescale/duracao/idioma da trilha",
    "hdlr": "Handler Box - tipo de trilha (vide/soun/etc)",
    "minf": "Media Information Box",
    "stbl": "Sample Table Box",
    "stsd": "Sample Description Box",
    "stts": "Decoding Time to Sample Box",
    "stss": "Sync Sample Box",
    "ctts": "Composition Time to Sample Box",
    "stsc": "Sample to Chunk Box",
    "stsz": "Sample Size Box",
    "stco": "Chunk Offset Box",
    "co64": "64-bit Chunk Offset Box",
    "udta": "User Data Box",
    "meta": "Metadata Box",
    "dinf": "Data Information Box",
    "edts": "Edit Box",
    "free": "Free Space Box",
    "skip": "Skip Box",
    "wide": "Wide Box",
    "mdat": "Media Data Box - dados brutos de audio/video",
}

CONTAINER_BOXES = frozenset(
    {
        "moov",
        "trak",
        "edts",
        "mdia",
        "minf",
        "stbl",
        "dinf",
        "udta",
        "meta",
        "moof",
        "traf",
        "mfra",
        "mvex",
        "ipro",
        "sinf",
        "schi",
        "ilst",
    }
)


def _decode_box_type(raw: bytes) -> str:
    try:
        return raw.decode("ascii")
    except UnicodeDecodeError:
        return raw.decode("latin-1", errors="replace")


def _read_full_box_header(data: bytes, offset: int = 0) -> Tuple[Optional[int], Optional[int]]:
    if len(data) < offset + 4:
        return None, None
    version = data[offset]
    flags = int.from_bytes(data[offset + 1 : offset + 4], byteorder="big")
    return version, flags


def _decode_language(code: int) -> str:
    letters = []
    for i in range(3):
        letters.append(chr(((code >> ((2 - i) * 5)) & 0x1F) + 0x60))
    return "".join(letters)


def _safe_unpack(fmt: str, data: bytes, offset: int = 0) -> Optional[Tuple[Any, ...]]:
    size = struct.calcsize(fmt)
    if len(data) < offset + size:
        return None
    return struct.unpack(fmt, data[offset : offset + size])


def _ascii_repr(byte: int) -> str:
    return chr(byte) if 32 <= byte <= 126 else "."


def _hex_dump_with_ascii(data: bytes, *, bytes_per_line: int = 16) -> Dict[str, Any]:
    """Dump estilo editor hex: offset | hex | ASCII."""
    lines: List[Dict[str, Any]] = []
    text_lines: List[str] = []
    hex_width = bytes_per_line * 3 - 1

    for offset in range(0, len(data), bytes_per_line):
        chunk = data[offset : offset + bytes_per_line]
        hex_part = " ".join(f"{b:02x}" for b in chunk).ljust(hex_width)
        ascii_part = "".join(_ascii_repr(b) for b in chunk).ljust(bytes_per_line)
        line_text = f"{offset:08x}  {hex_part}  |{ascii_part}|"
        lines.append({"offset": offset, "hex": hex_part.strip(), "ascii": ascii_part.rstrip(), "text": line_text})
        text_lines.append(line_text)

    return {
        "bytes_per_line": bytes_per_line,
        "lines": lines,
        "text": "\n".join(text_lines),
    }


def _payload_preview(data: bytes, *, total_size: Optional[int] = None, max_bytes: int = 512) -> Dict[str, Any]:
    sample = data[:max_bytes]
    if not sample:
        return {"mode": "empty", "value": ""}

    printable = sum(32 <= b <= 126 or b in (9, 10, 13) for b in sample)
    ratio = printable / len(sample)
    payload_total = int(total_size if total_size is not None else len(data))
    truncated = payload_total > len(sample)
    dump = _hex_dump_with_ascii(sample)

    base: Dict[str, Any] = {
        "truncated": truncated,
        "sample_bytes": len(sample),
        "total_bytes": payload_total,
        "hex_dump": dump["text"],
        "hex_dump_lines": dump["lines"],
    }

    if ratio >= 0.75:
        text = sample.decode("latin-1", errors="replace").replace("\x00", " ").strip()
        base.update({"mode": "text", "value": text})
        return base

    hex_str = sample.hex(" ")
    base.update({"mode": "hex", "value": hex_str})
    return base


def _parse_mvhd(payload: bytes) -> Dict[str, Any]:
    version, flags = _read_full_box_header(payload)
    if version is None:
        return {}
    if version == 1:
        values = _safe_unpack(">QQIQ", payload, 4)
        if not values:
            return {"version": version, "flags": flags}
        creation_time, modification_time, timescale, duration = values
    else:
        values = _safe_unpack(">IIII", payload, 4)
        if not values:
            return {"version": version, "flags": flags}
        creation_time, modification_time, timescale, duration = values
    return {
        "version": int(version),
        "flags": int(flags or 0),
        "creation_time": int(creation_time),
        "modification_time": int(modification_time),
        "timescale": int(timescale),
        "duration": int(duration),
    }


def _parse_tkhd(payload: bytes) -> Dict[str, Any]:
    version, flags = _read_full_box_header(payload)
    if version is None:
        return {}
    if version == 1:
        values = _safe_unpack(">QQIIQ", payload, 4)
        if not values:
            return {"version": version, "flags": flags}
        creation_time, modification_time, track_id, _, duration = values
    else:
        values = _safe_unpack(">IIIII", payload, 4)
        if not values:
            return {"version": version, "flags": flags}
        creation_time, modification_time, track_id, _, duration = values
    return {
        "version": int(version),
        "flags": int(flags or 0),
        "creation_time": int(creation_time),
        "modification_time": int(modification_time),
        "track_id": int(track_id),
        "duration": int(duration),
    }


def _parse_mdhd(payload: bytes) -> Dict[str, Any]:
    version, flags = _read_full_box_header(payload)
    if version is None:
        return {}
    if version == 1:
        values = _safe_unpack(">QQIQ", payload, 4)
        if not values:
            return {"version": version, "flags": flags}
        creation_time, modification_time, timescale, duration = values
        lang_offset = 4 + struct.calcsize(">QQIQ")
    else:
        values = _safe_unpack(">IIII", payload, 4)
        if not values:
            return {"version": version, "flags": flags}
        creation_time, modification_time, timescale, duration = values
        lang_offset = 4 + struct.calcsize(">IIII")
    lang_pair = _safe_unpack(">H", payload, lang_offset)
    language = _decode_language(lang_pair[0]) if lang_pair else "und"
    return {
        "version": int(version),
        "flags": int(flags or 0),
        "creation_time": int(creation_time),
        "modification_time": int(modification_time),
        "timescale": int(timescale),
        "duration": int(duration),
        "language": language,
    }


def _parse_hdlr(payload: bytes) -> Dict[str, Any]:
    version, flags = _read_full_box_header(payload)
    predef = _safe_unpack(">I", payload, 4)
    handler_raw = payload[8:12] if len(payload) >= 12 else b""
    reserved = _safe_unpack(">III", payload, 12)
    name_bytes = payload[24:] if len(payload) > 24 else b""
    if b"\x00" in name_bytes:
        name_bytes = name_bytes.split(b"\x00", 1)[0]
    name = name_bytes.decode("latin-1", errors="replace").strip()
    return {
        "version": int(version or 0),
        "flags": int(flags or 0),
        "pre_defined": int(predef[0]) if predef else 0,
        "handler_type": _decode_box_type(handler_raw) if handler_raw else "",
        "reserved": list(reserved) if reserved else [],
        "name": name,
    }


def _parse_box_fields(box_type: str, payload: bytes) -> Dict[str, Any]:
    if box_type == "mvhd":
        return _parse_mvhd(payload)
    if box_type == "tkhd":
        return _parse_tkhd(payload)
    if box_type == "mdhd":
        return _parse_mdhd(payload)
    if box_type == "hdlr":
        return _parse_hdlr(payload)
    return {}


def _read_box_header(file_obj, file_size: int) -> Optional[Dict[str, Any]]:
    start = file_obj.tell()
    if start + 8 > file_size:
        return None
    raw_header = file_obj.read(8)
    if len(raw_header) < 8:
        return None
    size32, box_type_raw = struct.unpack(">I4s", raw_header)
    box_type = _decode_box_type(box_type_raw)
    header_size = 8
    size = int(size32)
    if size32 == 1:
        ext = file_obj.read(8)
        if len(ext) < 8:
            return None
        size = int(struct.unpack(">Q", ext)[0])
        header_size = 16
    elif size32 == 0:
        size = file_size - start

    if size < header_size:
        return None

    end = min(file_size, start + size)
    return {
        "type": box_type,
        "offset": int(start),
        "size": int(size),
        "header_size": int(header_size),
        "end": int(end),
        "extended_size": bool(size32 == 1),
    }


def _parse_children(
    graph: nx.DiGraph,
    file_obj,
    *,
    file_size: int,
    parent_id: str,
    parent_path: str,
    end_offset: int,
    depth: int,
) -> None:
    while file_obj.tell() < end_offset:
        before = file_obj.tell()
        header = _read_box_header(file_obj, file_size)
        if header is None:
            file_obj.seek(end_offset)
            return
        if header["end"] <= header["offset"]:
            file_obj.seek(end_offset)
            return
        _parse_single_box(
            graph,
            file_obj,
            file_size=file_size,
            header=header,
            parent_id=parent_id,
            parent_path=parent_path,
            depth=depth,
        )
        if file_obj.tell() <= before:
            file_obj.seek(end_offset)
            return
    file_obj.seek(end_offset)


def _parse_single_box(
    graph: nx.DiGraph,
    file_obj,
    *,
    file_size: int,
    header: Dict[str, Any],
    parent_id: Optional[str],
    parent_path: str,
    depth: int,
) -> str:
    box_type = str(header["type"])
    offset = int(header["offset"])
    size = int(header["size"])
    end = int(header["end"])
    header_size = int(header["header_size"])
    payload_start = offset + header_size
    payload_end = max(payload_start, end)
    payload_size = max(0, payload_end - payload_start)
    node_id = f"{box_type}_{offset}"
    node_path = f"{parent_path}/{box_type}@{offset}"

    file_obj.seek(payload_start)
    sample_limit = 65536 if box_type in {"udta", "meta"} else 4096
    payload_sample = file_obj.read(min(payload_size, sample_limit))

    node_data: Dict[str, Any] = {
        "type": box_type,
        "size": size,
        "offset": offset,
        "end": end,
        "depth": depth,
        "path": node_path,
        "description": BOX_DESCRIPTIONS.get(box_type, "Box nao documentado"),
        "header_size": header_size,
        "payload_size": payload_size,
        "extended_size": bool(header.get("extended_size", False)),
    }

    parsed = _parse_box_fields(box_type, payload_sample)
    if parsed:
        node_data["fields"] = parsed

    if box_type in {"udta", "meta"}:
        node_data["payload_preview"] = _payload_preview(payload_sample, total_size=payload_size)

    graph.add_node(node_id, **node_data)
    if parent_id:
        graph.add_edge(parent_id, node_id)

    if box_type in CONTAINER_BOXES:
        child_start = payload_start
        if box_type == "meta" and payload_size >= 4:
            version, flags = _read_full_box_header(payload_sample)
            node_data.setdefault("fields", {})
            node_data["fields"]["version"] = int(version or 0)
            node_data["fields"]["flags"] = int(flags or 0)
            child_start += 4
            graph.nodes[node_id]["fields"] = node_data["fields"]

        file_obj.seek(child_start)
        _parse_children(
            graph,
            file_obj,
            file_size=file_size,
            parent_id=node_id,
            parent_path=node_path,
            end_offset=end,
            depth=depth + 1,
        )
    else:
        file_obj.seek(end)

    return node_id


def parse_iso_base_media(file_path: str) -> nx.DiGraph:
    graph = nx.DiGraph()
    file_size = os.path.getsize(file_path)
    with open(file_path, "rb") as file_obj:
        while file_obj.tell() < file_size:
            header = _read_box_header(file_obj, file_size)
            if header is None:
                break
            _parse_single_box(
                graph,
                file_obj,
                file_size=file_size,
                header=header,
                parent_id=None,
                parent_path="root",
                depth=0,
            )
    return graph


def _children_sorted(graph: nx.DiGraph, node_id: str) -> List[str]:
    return sorted(
        list(graph.successors(node_id)),
        key=lambda child: (int(graph.nodes[child].get("offset", 0)), child),
    )


def build_tree_json(graph: nx.DiGraph) -> List[Dict[str, Any]]:
    def build(node_id: str) -> Dict[str, Any]:
        node = graph.nodes[node_id]
        return {
            "id": node_id,
            "type": node.get("type"),
            "size": int(node.get("size", 0)),
            "offset": int(node.get("offset", 0)),
            "end": int(node.get("end", 0)),
            "path": str(node.get("path", node_id)),
            "description": node.get("description", ""),
            "fields": node.get("fields", {}),
            "children": [build(child) for child in _children_sorted(graph, node_id)],
        }

    roots = sorted(
        [node for node in graph.nodes if graph.in_degree(node) == 0],
        key=lambda node: (int(graph.nodes[node].get("offset", 0)), node),
    )
    return [build(root) for root in roots]


def render_tree_text(tree: Sequence[Dict[str, Any]]) -> str:
    lines: List[str] = []

    def walk(node: Dict[str, Any], depth: int) -> None:
        indent = "  " * depth
        lines.append(
            f"{indent}{node.get('type')}  "
            f"(offset={node.get('offset')}, size={node.get('size')})"
        )
        fields = node.get("fields") or {}
        for key in ("track_id", "handler_type", "timescale", "duration", "language"):
            if key in fields:
                lines.append(f"{indent}  - {key}: {fields.get(key)}")
        for child in node.get("children") or []:
            walk(child, depth + 1)

    for root in tree:
        walk(root, 0)
    return "\n".join(lines)


def collect_special_atoms(graph: nx.DiGraph, atom_type: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for node_id, data in graph.nodes(data=True):
        if data.get("type") != atom_type:
            continue
        preview = data.get("payload_preview") or {"mode": "empty", "value": ""}
        out.append(
            {
                "id": node_id,
                "path": data.get("path"),
                "offset": int(data.get("offset", 0)),
                "size": int(data.get("size", 0)),
                "preview_mode": preview.get("mode"),
                "preview": preview.get("value"),
                "preview_hex_dump": preview.get("hex_dump"),
                "preview_truncated": bool(preview.get("truncated", False)),
                "fields": data.get("fields", {}),
            }
        )
    return sorted(out, key=lambda item: (item["offset"], item["id"]))


def _extract_track_summaries(graph: nx.DiGraph) -> List[Dict[str, Any]]:
    tracks: List[Dict[str, Any]] = []
    for node_id, data in graph.nodes(data=True):
        if data.get("type") != "trak":
            continue
        summary: Dict[str, Any] = {
            "node_id": node_id,
            "path": data.get("path"),
            "offset": int(data.get("offset", 0)),
        }
        for child in nx.descendants(graph, node_id):
            child_data = graph.nodes[child]
            ctype = child_data.get("type")
            fields = child_data.get("fields") or {}
            if ctype == "tkhd":
                if "track_id" in fields:
                    summary["track_id"] = fields.get("track_id")
                if "duration" in fields:
                    summary["track_duration"] = fields.get("duration")
            elif ctype == "mdhd":
                if "timescale" in fields:
                    summary["timescale"] = fields.get("timescale")
                if "duration" in fields:
                    summary["duration"] = fields.get("duration")
                if "language" in fields:
                    summary["language"] = fields.get("language")
            elif ctype == "hdlr" and "handler_type" in fields:
                summary["handler_type"] = fields.get("handler_type")
                if fields.get("name"):
                    summary["handler_name"] = fields.get("name")
        tracks.append(summary)
    return sorted(tracks, key=lambda item: int(item.get("offset", 0)))


def build_metadata(graph: nx.DiGraph, file_path: str) -> Dict[str, Any]:
    top_level = sorted(
        [
            {
                "type": graph.nodes[node].get("type"),
                "offset": int(graph.nodes[node].get("offset", 0)),
                "size": int(graph.nodes[node].get("size", 0)),
                "path": graph.nodes[node].get("path"),
            }
            for node in graph.nodes
            if graph.in_degree(node) == 0
        ],
        key=lambda item: (item["offset"], item["type"]),
    )
    counter = Counter(str(data.get("type")) for _, data in graph.nodes(data=True))
    mvhd_fields = next(
        (
            graph.nodes[node].get("fields")
            for node, data in graph.nodes(data=True)
            if data.get("type") == "mvhd" and graph.nodes[node].get("fields")
        ),
        {},
    )
    tracks = _extract_track_summaries(graph)
    max_depth = max((int(data.get("depth", 0)) for _, data in graph.nodes(data=True)), default=0)

    return {
        "file_name": Path(file_path).name,
        "file_path": str(file_path),
        "file_size": os.path.getsize(file_path),
        "box_count": graph.number_of_nodes(),
        "edge_count": graph.number_of_edges(),
        "max_depth": max_depth,
        "top_level_boxes": top_level,
        "box_type_counts": dict(sorted(counter.items())),
        "creation_time": mvhd_fields.get("creation_time"),
        "modification_time": mvhd_fields.get("modification_time"),
        "timescale": mvhd_fields.get("timescale"),
        "duration": mvhd_fields.get("duration"),
        "tracks": tracks,
    }


def _metadata_as_text(metadata: Dict[str, Any]) -> str:
    lines = [
        "ISO BMFF - RELATORIO ESTRUTURAL",
        f"Arquivo: {metadata.get('file_name')}",
        f"Tamanho (bytes): {metadata.get('file_size')}",
        f"Boxes: {metadata.get('box_count')} | Profundidade maxima: {metadata.get('max_depth')}",
        "",
        "Cabecalho movie (mvhd):",
        f"  creation_time: {metadata.get('creation_time')}",
        f"  modification_time: {metadata.get('modification_time')}",
        f"  timescale: {metadata.get('timescale')}",
        f"  duration: {metadata.get('duration')}",
        "",
        "Top-level boxes:",
    ]
    for item in metadata.get("top_level_boxes", []):
        lines.append(f"  - {item.get('type')} @ {item.get('offset')} ({item.get('size')} bytes)")

    lines.append("")
    lines.append("Trilhas:")
    tracks = metadata.get("tracks", [])
    if not tracks:
        lines.append("  - Nenhuma trilha identificada")
    else:
        for track in tracks:
            lines.append(
                "  - track_id={track_id} handler={handler} timescale={timescale} "
                "duration={duration} language={lang}".format(
                    track_id=track.get("track_id", "?"),
                    handler=track.get("handler_type", "?"),
                    timescale=track.get("timescale", "?"),
                    duration=track.get("duration", "?"),
                    lang=track.get("language", "?"),
                )
            )
    return "\n".join(lines)


def run_isomedia_parser(video_path: str, out_dir: Path, reporter: ProgressFn = None) -> Dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    if reporter:
        reporter(8, "Parseando boxes ISO BMFF")

    graph = parse_iso_base_media(video_path)
    if graph.number_of_nodes() == 0:
        raise ValueError("Formato nao suportado ou arquivo sem boxes ISO BMFF validos")

    if reporter:
        reporter(38, "Montando arvore e metadados")

    tree = build_tree_json(graph)
    tree_txt = render_tree_text(tree)
    metadata = build_metadata(graph, video_path)
    udta_atoms = collect_special_atoms(graph, "udta")
    meta_atoms = collect_special_atoms(graph, "meta")

    if reporter:
        reporter(65, "Salvando artefatos")

    graph_path = out_dir / "isom_structure_graph.json"
    tree_json_path = out_dir / "isom_tree.json"
    tree_txt_path = out_dir / "isom_tree.txt"
    metadata_json_path = out_dir / "isom_metadata.json"
    metadata_txt_path = out_dir / "isom_metadata.txt"
    udta_json_path = out_dir / "udta_atoms.json"
    meta_atoms_json_path = out_dir / "meta_atoms.json"

    with open(graph_path, "w", encoding="utf-8") as f:
        json.dump(json_graph.node_link_data(graph), f, ensure_ascii=False, indent=2)
    tree_json_path.write_text(json.dumps(tree, ensure_ascii=False, indent=2), encoding="utf-8")
    tree_txt_path.write_text(tree_txt, encoding="utf-8")
    metadata_json_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    metadata_txt_path.write_text(_metadata_as_text(metadata), encoding="utf-8")
    udta_json_path.write_text(json.dumps(udta_atoms, ensure_ascii=False, indent=2), encoding="utf-8")
    meta_atoms_json_path.write_text(json.dumps(meta_atoms, ensure_ascii=False, indent=2), encoding="utf-8")

    if reporter:
        reporter(84, "Parser ISO BMFF concluido")

    return {
        "box_count": graph.number_of_nodes(),
        "depth": metadata.get("max_depth", 0),
        "graph_node_link": json_graph.node_link_data(graph),
        "tree": tree,
        "metadata": metadata,
        "udta_atoms": udta_atoms,
        "meta_atoms": meta_atoms,
        "isom_structure_graph_path": str(graph_path),
        "isom_tree_json_path": str(tree_json_path),
        "isom_tree_txt_path": str(tree_txt_path),
        "isom_metadata_json_path": str(metadata_json_path),
        "isom_metadata_txt_path": str(metadata_txt_path),
        "isom_udta_json_path": str(udta_json_path),
        "isom_meta_atoms_json_path": str(meta_atoms_json_path),
        "metadata_report_path": str(metadata_txt_path),
    }
