"""Extracao de metadados de audio (ExifTool + probe tecnico)."""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from forensics.audio.audio_probe import probe_audio_metadata
from core.metadata.c2pa_extract import extract_c2pa_manifest, is_c2pa_exiftool_tag
from core.metadata.forensic_metadata_insights import build_forensic_insights

_EMPTY_FAMILIES = ("id3", "vorbis", "riff", "quicktime", "xmp", "c2pa", "file", "other")

# Prefixo ExifTool → família forense de áudio
_PREFIX_FAMILY: dict[str, str] = {
    "ID3": "id3",
    "ID3v1": "id3",
    "ID3v2": "id3",
    "ID3v2_2": "id3",
    "ID3v2_3": "id3",
    "ID3v2_4": "id3",
    "Vorbis": "vorbis",
    "FLAC": "vorbis",
    "Opus": "vorbis",
    "Speex": "vorbis",
    "RIFF": "riff",
    "WAV": "riff",
    "AIFF": "riff",
    "QuickTime": "quicktime",
    "ItemList": "quicktime",
    "Keys": "quicktime",
    "Track": "quicktime",
    "Track1": "quicktime",
    "Track2": "quicktime",
    "Track3": "quicktime",
    "MPEG": "other",
    "ASF": "other",
    "APE": "other",
    "XMP": "xmp",
    "File": "file",
    "Composite": "file",
    "System": "file",
    "ExifTool": "file",
}


def _empty_families() -> dict[str, list[dict[str, str]]]:
    return {k: [] for k in _EMPTY_FAMILIES}


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


def _exiftool_available() -> bool:
    return shutil.which("exiftool") is not None or shutil.which("exiftool.exe") is not None


def _classify_audio_tag(tag: str) -> str:
    if is_c2pa_exiftool_tag(tag):
        return "c2pa"
    if ":" in tag:
        prefix = tag.split(":", 1)[0]
        if prefix in _PREFIX_FAMILY:
            return _PREFIX_FAMILY[prefix]
        if prefix.startswith("ID3"):
            return "id3"
        if prefix.startswith("Track"):
            return "quicktime"
        if prefix.startswith("XMP"):
            return "xmp"
        if prefix in ("C2PA", "JUMBF"):
            return "c2pa"
        pl = prefix.lower()
        if "vorbis" in pl or "flac" in pl or "opus" in pl:
            return "vorbis"
        if "riff" in pl or "wav" in pl:
            return "riff"
        if "quicktime" in pl or "itunes" in pl or "itemlist" in pl:
            return "quicktime"
    tag_l = tag.lower()
    if tag_l.startswith("id3") or "id3" in tag_l:
        return "id3"
    return "other"


def _tag_entry(tag: str, value: Any, source: str) -> dict[str, str]:
    group = _classify_audio_tag(tag)
    return {
        "tag": tag,
        "value": _safe_str(value),
        "group": group,
        "source": source,
    }


def _read_exiftool_audio(path: str) -> dict[str, Any]:
    import exiftool

    families = _empty_families()
    warnings: list[str] = []

    with exiftool.ExifToolHelper() as et:
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
    }


def _forensic_highlights(families: dict[str, list[dict[str, str]]]) -> list[dict[str, str]]:
    keys_of_interest = (
        "title",
        "artist",
        "album",
        "encoder",
        "software",
        "create",
        "date",
        "duration",
        "sample",
        "channel",
        "bitrate",
        "vendor",
        "comment",
        "genre",
        "track",
        "composer",
        "copyright",
        "tool",
        "handler",
        "majorbrand",
        "compatible",
        "c2pa",
        "claim",
        "jumbf",
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
    return highlights[:50]


def _build_insights(
    families: dict[str, list[dict[str, str]]],
    probe: dict[str, Any],
    warnings: list[str],
) -> list[dict[str, str]]:
    insights: list[dict[str, str]] = []
    all_tags = [e for entries in families.values() for e in entries]
    tag_blob = " ".join(e["tag"].lower() for e in all_tags)

    if not all_tags and not probe:
        insights.append(
            {
                "severity": "medium",
                "title": "Poucos metadados extraídos",
                "detail": "O arquivo não expôs tags ExifTool nem probe técnico útil.",
            }
        )

    encoder_hits = [e for e in all_tags if "encoder" in e["tag"].lower() or "software" in e["tag"].lower()]
    if encoder_hits:
        insights.append(
            {
                "severity": "info",
                "title": "Encoder / software identificado",
                "detail": "; ".join(f"{e['tag']}={e['value']}" for e in encoder_hits[:4]),
                "tags": [e["tag"] for e in encoder_hits[:6]],
            }
        )

    if "id3" in families and families["id3"] and "vorbis" in families and families["vorbis"]:
        insights.append(
            {
                "severity": "medium",
                "title": "Múltiplos sistemas de tags",
                "detail": "Há tags ID3 e Vorbis/Opus/FLAC no mesmo fluxo — possível remux ou conversão.",
            }
        )

    if probe.get("codec"):
        insights.append(
            {
                "severity": "info",
                "title": "Codec técnico",
                "detail": (
                    f"Codec={probe.get('codec')}; "
                    f"sr={probe.get('sample_rate_hz')}; "
                    f"canais={probe.get('channels')}; "
                    f"duração={probe.get('duration_sec')}s"
                ),
            }
        )

    if "whatsapp" in tag_blob or "telegram" in tag_blob:
        insights.append(
            {
                "severity": "high",
                "title": "Indício de app de mensagem",
                "detail": "Tags sugerem origem em aplicativo de mensagens (verificar parser estrutural).",
            }
        )

    for w in warnings:
        insights.append({"severity": "medium", "title": "Aviso do extrator", "detail": w})

    return insights


def extract_audio_metadata(path: str) -> dict[str, Any]:
    """Extrai metadados de arquivo de áudio via ExifTool + probe técnico."""
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
            exif_meta = _read_exiftool_audio(path)
            families = exif_meta["families"]
            engines.extend(exif_meta.get("engines") or ["exiftool"])
            warnings.extend(exif_meta.get("warnings") or [])
        except Exception as exc:
            warnings.append(f"ExifTool falhou ({exc}).")
    else:
        warnings.append(
            "ExifTool nao encontrado no PATH — instale o binario exiftool para tags ID3/Vorbis/RIFF/QuickTime."
        )

    probe = probe_audio_metadata(path) or {}
    if probe:
        engines.append("audio_probe")
        file_info.update(
            {
                "codec": probe.get("codec"),
                "sample_rate_hz": probe.get("sample_rate_hz"),
                "channels": probe.get("channels"),
                "bit_depth": probe.get("bit_depth"),
                "duration_sec": probe.get("duration_sec"),
            }
        )

    c2pa_structured = extract_c2pa_manifest(path)
    c2pa_for_meta = {k: v for k, v in c2pa_structured.items() if k != "store"}
    c2pa_families = c2pa_structured.get("families") or {}
    if c2pa_families.get("c2pa"):
        families.setdefault("c2pa", [])
        # Prefere entradas c2pa-python; evita duplicar depois se ExifTool tambem reportar
        existing = {e["tag"] for e in families["c2pa"]}
        for entry in c2pa_families["c2pa"]:
            if entry["tag"] not in existing:
                families["c2pa"].append(entry)
        families["c2pa"].sort(key=lambda e: e["tag"].lower())
    if c2pa_structured.get("engine") and c2pa_structured.get("available"):
        if "c2pa-python" not in engines:
            engines.append("c2pa-python")
    elif c2pa_structured.get("reason"):
        warnings.append(str(c2pa_structured["reason"]))
    elif c2pa_structured.get("error"):
        warnings.append(f"C2PA: {c2pa_structured['error']}")

    highlights = _forensic_highlights(families)
    counts = {k: len(families.get(k, [])) for k in _EMPTY_FAMILIES}
    summary = {
        "metadata_engine": "+".join(engines) if engines else "none",
        "metadata_engines": engines,
        "tag_counts": counts,
        "total_tags": sum(counts.values()),
        "has_id3": counts.get("id3", 0) > 0,
        "has_vorbis": counts.get("vorbis", 0) > 0,
        "has_riff": counts.get("riff", 0) > 0,
        "has_quicktime": counts.get("quicktime", 0) > 0,
        "has_xmp": counts.get("xmp", 0) > 0,
        "has_c2pa": bool(c2pa_for_meta.get("present")),
        "c2pa_available": bool(c2pa_for_meta.get("available")),
        "c2pa_valid": c2pa_for_meta.get("is_valid"),
        "c2pa_validation_state": c2pa_for_meta.get("validation_state"),
        "codec": probe.get("codec") or file_info.get("codec"),
        "sample_rate_hz": probe.get("sample_rate_hz"),
        "channels": probe.get("channels"),
        "duration_sec": probe.get("duration_sec"),
        "bit_depth": probe.get("bit_depth"),
        "exiftool_available": _exiftool_available(),
    }
    insights = _build_insights(families, probe, warnings)
    c2pa_insights = build_forensic_insights(
        families,
        {},
        summary,
        c2pa_structured=c2pa_for_meta,
    )
    # Mantem insights de audio e acrescenta os de C2PA (sem duplicar titulos)
    seen_titles = {i.get("title") for i in insights}
    for item in c2pa_insights:
        if item.get("title") not in seen_titles:
            insights.append(item)

    return {
        "success": True,
        "adapter": "audio_metadata",
        "status": "completed",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "file": file_info,
        "summary": summary,
        "highlights": highlights,
        "forensic_insights": insights,
        "probe": probe,
        "c2pa_structured": c2pa_structured,
        "metadata": {
            "engine": summary["metadata_engine"],
            "engines": engines,
            "available": True,
            "families": families,
            "warnings": warnings,
            "c2pa_structured": c2pa_for_meta,
        },
    }
