"""Extracao profunda de metadados de video (ExifTool + ffprobe + ISO BMFF leve)."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_EMPTY_FAMILIES = (
    "quicktime",
    "streams",
    "gps",
    "camera",
    "codec",
    "xmp",
    "container",
    "file",
    "other",
)

_CAMERA_PREFIXES = frozenset(
    {
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
        "Samsung",
        "Ricoh",
        "Kodak",
        "Minolta",
        "Sigma",
        "Insta360",
        "Garmin",
        "Android",
    }
)

_CODEC_PREFIXES = frozenset(
    {
        "H264",
        "AVC",
        "HEVC",
        "H265",
        "VP8",
        "VP9",
        "AV1",
        "MPEG",
        "MPEG4",
        "Theora",
        "ProRes",
        "MXF",
    }
)

_CONTAINER_PREFIXES = frozenset(
    {
        "Matroska",
        "RIFF",
        "ASF",
        "FlashPix",
        "Real",
        "Ogg",
        "FLV",
        "WebM",
        "AVI",
        "DIVX",
    }
)

_QUICKTIME_PREFIXES = frozenset(
    {
        "QuickTime",
        "ItemList",
        "Keys",
        "Track",
        "Track1",
        "Track2",
        "Track3",
        "Track4",
        "Track5",
        "Track6",
        "Movie",
        "UserData",
        "Meta",
    }
)

# ISO BMFF resumido: evita custo em arquivos enormes no job de metadados.
_ISOM_MAX_BYTES = 2 * 1024 * 1024 * 1024  # 2 GiB


def _empty_families() -> dict[str, list[dict[str, str]]]:
    return {k: [] for k in _EMPTY_FAMILIES}


def _safe_str(value: Any, max_len: int = 8192) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        try:
            text = json.dumps(value, ensure_ascii=False, default=str)
        except Exception:
            text = str(value)
    elif isinstance(value, bytes):
        try:
            text = value.decode("utf-8", errors="replace")
        except Exception:
            text = repr(value[:200])
    else:
        text = str(value)
    if len(text) > max_len:
        return text[: max_len - 3] + "..."
    return text


def _exiftool_available() -> bool:
    return shutil.which("exiftool") is not None or shutil.which("exiftool.exe") is not None


def _ffprobe_available() -> bool:
    return shutil.which("ffprobe") is not None


def _classify_video_tag(tag: str) -> str:
    if ":" in tag:
        prefix = tag.split(":", 1)[0]
        if prefix.startswith("Track"):
            return "quicktime"
        if prefix in _QUICKTIME_PREFIXES or prefix.startswith("QuickTime"):
            return "quicktime"
        if prefix in _CAMERA_PREFIXES:
            return "camera"
        if prefix in _CODEC_PREFIXES:
            return "codec"
        if prefix in _CONTAINER_PREFIXES:
            return "container"
        if prefix.startswith("XMP") or prefix == "XMP":
            return "xmp"
        if prefix in ("File", "Composite", "System", "ExifTool"):
            return "file"
        if prefix == "GPS" or prefix.startswith("GPS"):
            return "gps"
        pl = prefix.lower()
        if "gps" in pl or "location" in pl:
            return "gps"
        if "gopro" in pl or "dji" in pl or "maker" in pl:
            return "camera"
    tag_l = tag.lower()
    if "gps" in tag_l or "latitude" in tag_l or "longitude" in tag_l:
        return "gps"
    if tag_l.startswith("ffprobe:"):
        return "streams"
    return "other"


def _tag_entry(tag: str, value: Any, source: str) -> dict[str, str]:
    group = _classify_video_tag(tag)
    return {
        "tag": tag,
        "value": _safe_str(value),
        "group": group,
        "source": source,
    }


def _read_exiftool_video(path: str) -> dict[str, Any]:
    """ExifTool profundo: grupos, duplicatas, tags desconhecidas e metadados embutidos (-ee)."""
    import exiftool

    families = _empty_families()
    warnings: list[str] = []

    # -G1 group names, -a duplicates, -u unknown, -ee embedded (critico em video)
    with exiftool.ExifToolHelper(common_args=["-G1", "-a", "-u", "-ee", "-n"]) as et:
        blocks = et.get_metadata(path)

    for block in blocks:
        for tag, value in block.items():
            if tag in ("SourceFile", "ExifTool:ExifToolVersion"):
                continue
            entry = _tag_entry(tag, value, "exiftool")
            group = entry["group"] if entry["group"] in families else "other"
            families[group].append(entry)

    for key in families:
        families[key].sort(key=lambda e: e["tag"].lower())

    return {
        "engine": "exiftool",
        "engines": ["exiftool"],
        "available": True,
        "families": families,
        "warnings": warnings,
        "block_count": len(blocks),
    }


def _probe_ffprobe(path: str) -> dict[str, Any]:
    if not _ffprobe_available():
        return {"available": False, "reason": "ffprobe ausente no PATH"}

    cmd = [
        "ffprobe",
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        "-show_chapters",
        path,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=False)
    except subprocess.TimeoutExpired:
        return {"available": False, "reason": "ffprobe timeout (>120s)"}
    except Exception as exc:
        return {"available": False, "reason": str(exc)}

    if proc.returncode != 0:
        return {
            "available": False,
            "reason": (proc.stderr or proc.stdout or "ffprobe falhou")[:500],
        }

    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        return {"available": False, "reason": f"JSON ffprobe invalido: {exc}"}

    fmt = data.get("format") or {}
    streams = data.get("streams") or []
    chapters = data.get("chapters") or []

    video_streams = [s for s in streams if s.get("codec_type") == "video"]
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
    primary = video_streams[0] if video_streams else {}

    summary = {
        "available": True,
        "format_name": fmt.get("format_name"),
        "format_long_name": fmt.get("format_long_name"),
        "duration_sec": _to_float(fmt.get("duration")),
        "size_bytes": _to_int(fmt.get("size")),
        "bit_rate": _to_int(fmt.get("bit_rate")),
        "nb_streams": _to_int(fmt.get("nb_streams")) or len(streams),
        "nb_programs": _to_int(fmt.get("nb_programs")),
        "tags": fmt.get("tags") or {},
        "video_stream_count": len(video_streams),
        "audio_stream_count": len(audio_streams),
        "chapter_count": len(chapters),
        "width": _to_int(primary.get("width")),
        "height": _to_int(primary.get("height")),
        "codec_name": primary.get("codec_name"),
        "codec_long_name": primary.get("codec_long_name"),
        "pix_fmt": primary.get("pix_fmt"),
        "avg_frame_rate": primary.get("avg_frame_rate"),
        "r_frame_rate": primary.get("r_frame_rate"),
        "streams": streams,
        "chapters": chapters,
    }
    return summary


def _to_float(value: Any) -> float | None:
    try:
        if value is None or value == "N/A":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    try:
        if value is None or value == "N/A":
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _ffprobe_as_family_entries(probe: dict[str, Any]) -> list[dict[str, str]]:
    if not probe.get("available"):
        return []
    entries: list[dict[str, str]] = []
    for key in (
        "format_name",
        "format_long_name",
        "duration_sec",
        "bit_rate",
        "nb_streams",
        "width",
        "height",
        "codec_name",
        "codec_long_name",
        "pix_fmt",
        "avg_frame_rate",
        "r_frame_rate",
        "video_stream_count",
        "audio_stream_count",
        "chapter_count",
    ):
        if probe.get(key) is not None:
            entries.append(_tag_entry(f"ffprobe:format.{key}", probe[key], "ffprobe"))

    for i, stream in enumerate(probe.get("streams") or []):
        stype = stream.get("codec_type", "unknown")
        for key in (
            "index",
            "codec_name",
            "codec_long_name",
            "profile",
            "width",
            "height",
            "pix_fmt",
            "sample_rate",
            "channels",
            "channel_layout",
            "bit_rate",
            "duration",
            "nb_frames",
            "avg_frame_rate",
            "r_frame_rate",
            "time_base",
            "start_time",
            "tags",
        ):
            if key in stream and stream[key] is not None:
                entries.append(
                    _tag_entry(f"ffprobe:stream[{i}:{stype}].{key}", stream[key], "ffprobe")
                )
    return entries


def _isom_container_summary(path: str) -> dict[str, Any]:
    size = Path(path).stat().st_size
    if size > _ISOM_MAX_BYTES:
        return {
            "available": False,
            "reason": f"Arquivo > {_ISOM_MAX_BYTES // (1024**3)} GiB — resumo ISO BMFF omitido no job de metadados",
        }
    suffix = Path(path).suffix.lower()
    if suffix not in {".mp4", ".m4v", ".mov", ".m4a", ".3gp", ".3g2", ".f4v", ".qt"}:
        # Ainda tenta: muitos videos sao BMFF sem extensao tipica
        pass
    try:
        from forensics.video.isom_parser import build_metadata, parse_iso_base_media

        graph = parse_iso_base_media(path)
        meta = build_metadata(graph, path)
        return {
            "available": True,
            "box_count": meta.get("box_count"),
            "max_depth": meta.get("max_depth"),
            "creation_time": meta.get("creation_time"),
            "modification_time": meta.get("modification_time"),
            "timescale": meta.get("timescale"),
            "duration": meta.get("duration"),
            "top_level_boxes": meta.get("top_level_boxes"),
            "tracks": meta.get("tracks"),
        }
    except Exception as exc:
        logger.debug("ISO BMFF summary falhou para %s: %s", path, exc)
        return {"available": False, "reason": str(exc)}


def _isom_as_family_entries(isom: dict[str, Any]) -> list[dict[str, str]]:
    if not isom.get("available"):
        return []
    entries: list[dict[str, str]] = []
    for key in (
        "box_count",
        "max_depth",
        "creation_time",
        "modification_time",
        "timescale",
        "duration",
    ):
        if isom.get(key) is not None:
            entries.append(_tag_entry(f"isom:{key}", isom[key], "isom_parser"))
    for i, track in enumerate(isom.get("tracks") or []):
        for key, value in (track or {}).items():
            if value is not None:
                entries.append(_tag_entry(f"isom:track[{i}].{key}", value, "isom_parser"))
    top = isom.get("top_level_boxes") or []
    if top:
        entries.append(_tag_entry("isom:top_level_boxes", top, "isom_parser"))
    return entries


def _forensic_highlights(families: dict[str, list[dict[str, str]]]) -> list[dict[str, str]]:
    keys_of_interest = (
        "create",
        "modify",
        "date",
        "make",
        "model",
        "software",
        "encoder",
        "gps",
        "latitude",
        "longitude",
        "altitude",
        "duration",
        "width",
        "height",
        "codec",
        "handler",
        "com.apple",
        "gopro",
        "dji",
        "android",
        "compatible",
        "majorbrand",
        "compressor",
        "rotation",
        "orientation",
        "serial",
        "firmware",
    )
    highlights: list[dict[str, str]] = []
    seen: set[str] = set()
    for group, entries in families.items():
        for entry in entries:
            tag_l = entry["tag"].lower()
            norm = tag_l.split(":")[-1]
            if norm in seen:
                continue
            if any(k in tag_l for k in keys_of_interest):
                seen.add(norm)
                highlights.append({**entry, "family": group})
    return highlights[:60]


def _build_insights(
    families: dict[str, list[dict[str, str]]],
    ffprobe: dict[str, Any],
    isom: dict[str, Any],
    warnings: list[str],
) -> list[dict[str, str]]:
    insights: list[dict[str, str]] = []
    all_tags = [e for entries in families.values() for e in entries]
    blob = " ".join(f"{e['tag']}={e['value']}".lower() for e in all_tags)

    if families.get("gps"):
        insights.append(
            {
                "severity": "high",
                "title": "Geolocalização presente",
                "detail": f"{len(families['gps'])} tag(s) GPS/localização — verificar origem e possível remoção parcial.",
                "tags": [e["tag"] for e in families["gps"][:8]],
            }
        )

    if families.get("camera"):
        cams = families["camera"]
        insights.append(
            {
                "severity": "info",
                "title": "Metadados de câmera / MakerNotes",
                "detail": f"{len(cams)} tags de fabricante/dispositivo.",
                "tags": [e["tag"] for e in cams[:8]],
            }
        )

    for needle, title in (
        ("gopro", "Assinatura GoPro"),
        ("dji", "Assinatura DJI"),
        ("insta360", "Assinatura Insta360"),
        ("android", "Indício Android / app"),
        ("com.apple", "Indício Apple / QuickTime"),
    ):
        if needle in blob:
            insights.append(
                {
                    "severity": "medium",
                    "title": title,
                    "detail": f"Tags/valores contêm '{needle}'.",
                }
            )

    create_vals = [
        e["value"]
        for e in all_tags
        if "create" in e["tag"].lower() and "date" in e["tag"].lower()
    ]
    modify_vals = [
        e["value"]
        for e in all_tags
        if "modif" in e["tag"].lower() and "date" in e["tag"].lower()
    ]
    if create_vals and modify_vals and set(create_vals) != set(modify_vals):
        insights.append(
            {
                "severity": "medium",
                "title": "Datas de criação e modificação divergentes",
                "detail": f"create≈{create_vals[0]}; modify≈{modify_vals[0]}",
            }
        )

    if isom.get("available") and isom.get("creation_time") and isom.get("modification_time"):
        if isom["creation_time"] != isom["modification_time"]:
            insights.append(
                {
                    "severity": "info",
                    "title": "ISO BMFF: creation ≠ modification",
                    "detail": (
                        f"creation_time={isom['creation_time']}; "
                        f"modification_time={isom['modification_time']}"
                    ),
                }
            )

    if ffprobe.get("available"):
        insights.append(
            {
                "severity": "info",
                "title": "Streams (ffprobe)",
                "detail": (
                    f"vídeo={ffprobe.get('video_stream_count')}, "
                    f"áudio={ffprobe.get('audio_stream_count')}, "
                    f"codec={ffprobe.get('codec_name')}, "
                    f"{ffprobe.get('width')}x{ffprobe.get('height')}, "
                    f"duração={ffprobe.get('duration_sec')}s"
                ),
            }
        )

    if not all_tags and not ffprobe.get("available"):
        insights.append(
            {
                "severity": "medium",
                "title": "Metadados escassos",
                "detail": "Poucas tags ExifTool e ffprobe indisponível/falhou.",
            }
        )

    for w in warnings:
        insights.append({"severity": "medium", "title": "Aviso do extrator", "detail": w})

    return insights


def extract_video_metadata(path: str) -> dict[str, Any]:
    """Extrai metadados profundos de video: ExifTool + ffprobe + resumo ISO BMFF."""
    p = Path(path)
    if not p.is_file():
        return {"success": False, "error": f"Arquivo nao encontrado: {path}"}

    file_info: dict[str, Any] = {
        "filename": p.name,
        "suffix": p.suffix.lower(),
        "size_bytes": p.stat().st_size,
    }

    warnings: list[str] = []
    engines: list[str] = []
    families = _empty_families()

    if _exiftool_available():
        try:
            exif_meta = _read_exiftool_video(path)
            families = exif_meta["families"]
            engines.extend(exif_meta.get("engines") or ["exiftool"])
            warnings.extend(exif_meta.get("warnings") or [])
            file_info["exiftool_blocks"] = exif_meta.get("block_count")
        except Exception as exc:
            warnings.append(f"ExifTool falhou ({exc}).")
    else:
        warnings.append(
            "ExifTool nao encontrado no PATH — tags QuickTime/GPS/MakerNotes/XMP ficam indisponiveis."
        )

    ffprobe = _probe_ffprobe(path)
    if ffprobe.get("available"):
        engines.append("ffprobe")
        for entry in _ffprobe_as_family_entries(ffprobe):
            families["streams"].append(entry)
        families["streams"].sort(key=lambda e: e["tag"].lower())
        file_info.update(
            {
                "duration_sec": ffprobe.get("duration_sec"),
                "width": ffprobe.get("width"),
                "height": ffprobe.get("height"),
                "codec_name": ffprobe.get("codec_name"),
                "format_name": ffprobe.get("format_name"),
                "bit_rate": ffprobe.get("bit_rate"),
            }
        )
    else:
        warnings.append(f"ffprobe: {ffprobe.get('reason') or 'indisponivel'}")

    isom = _isom_container_summary(path)
    if isom.get("available"):
        engines.append("isom_parser")
        for entry in _isom_as_family_entries(isom):
            families["container"].append(entry)
        families["container"].sort(key=lambda e: e["tag"].lower())
    elif isom.get("reason"):
        warnings.append(f"ISO BMFF: {isom['reason']}")

    highlights = _forensic_highlights(families)
    counts = {k: len(families.get(k, [])) for k in _EMPTY_FAMILIES}
    summary = {
        "metadata_engine": "+".join(engines) if engines else "none",
        "metadata_engines": engines,
        "tag_counts": counts,
        "total_tags": sum(counts.values()),
        "has_gps": counts.get("gps", 0) > 0,
        "has_camera": counts.get("camera", 0) > 0,
        "has_xmp": counts.get("xmp", 0) > 0,
        "has_quicktime": counts.get("quicktime", 0) > 0,
        "duration_sec": file_info.get("duration_sec"),
        "width": file_info.get("width"),
        "height": file_info.get("height"),
        "codec_name": file_info.get("codec_name"),
        "format_name": file_info.get("format_name"),
        "bit_rate": file_info.get("bit_rate"),
        "exiftool_available": _exiftool_available(),
        "ffprobe_available": _ffprobe_available(),
        "isom_available": bool(isom.get("available")),
    }
    insights = _build_insights(families, ffprobe, isom, warnings)

    # Payload ffprobe/isom sem streams completos no JSON principal (evitar gigantes);
    # streams detalhados ja estao em families.streams.
    ffprobe_public = {
        k: v
        for k, v in ffprobe.items()
        if k not in ("streams", "chapters")
    }
    if ffprobe.get("available"):
        ffprobe_public["stream_summaries"] = [
            {
                "index": s.get("index"),
                "codec_type": s.get("codec_type"),
                "codec_name": s.get("codec_name"),
                "width": s.get("width"),
                "height": s.get("height"),
                "sample_rate": s.get("sample_rate"),
                "channels": s.get("channels"),
            }
            for s in (ffprobe.get("streams") or [])
        ]

    return {
        "success": True,
        "adapter": "video_metadata",
        "status": "completed",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "file": file_info,
        "summary": summary,
        "highlights": highlights,
        "forensic_insights": insights,
        "ffprobe": ffprobe_public,
        "isom": {k: v for k, v in isom.items() if k != "tracks"} | {
            "track_count": len(isom.get("tracks") or []) if isom.get("available") else 0,
            "tracks": isom.get("tracks") if isom.get("available") else [],
        },
        "metadata": {
            "engine": summary["metadata_engine"],
            "engines": engines,
            "available": True,
            "families": families,
            "warnings": warnings,
        },
    }
