"""Resultados e artefatos dos parsers de container de áudio (MP3 / Ogg Opus).

Os motores em ``mp3_parser`` / ``opus_parser`` são intocáveis; este módulo só
orquestra saída JSON/TXT para jobs e UI.
"""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from core.job_staging import job_artifact_dir


def _safe_json(obj: Any) -> Any:
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, bytes):
        return {"_type": "bytes", "length": len(obj)}
    if is_dataclass(obj):
        return _safe_json(asdict(obj))
    if isinstance(obj, dict):
        return {str(k): _safe_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_safe_json(v) for v in obj]
    return str(obj)


def _write_artifacts(
    out_dir: Path,
    *,
    report: str,
    summary: dict[str, Any],
) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "container_parser_report.txt"
    summary_path = out_dir / "container_parser_summary.json"
    report_path.write_text(report, encoding="utf-8")
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return {
        "container_report_txt_path": str(report_path),
        "container_summary_json_path": str(summary_path),
    }


def _mp3_encoder(analyzer: Any) -> str:
    if analyzer.vbr_header and analyzer.vbr_header.get("encoder"):
        return str(analyzer.vbr_header["encoder"])
    id3v2 = analyzer.id3v2 or {}
    frames = id3v2.get("frames") or {}
    for key in ("TENC", "TSSE"):
        if key in frames and isinstance(frames[key], dict) and frames[key].get("text"):
            return str(frames[key]["text"])
    return "Desconhecido"


def _mp3_findings(analyzer: Any) -> list[str]:
    findings: list[str] = []
    bitrates = list({f.bitrate for f in analyzer.frames}) if analyzer.frames else []
    versions = {f.version for f in analyzer.frames} if analyzer.frames else set()
    samplerates = {f.samplerate for f in analyzer.frames} if analyzer.frames else set()

    if len(bitrates) > 1 and not analyzer.vbr_header:
        findings.append("Múltiplos bitrates sem header VBR (Xing/VBRI) — possível concatenação")
    if len(versions) > 1:
        findings.append(f"Múltiplas versões MPEG no mesmo arquivo: {sorted(versions)}")
    if len(samplerates) > 1:
        findings.append(f"Múltiplas sample rates: {sorted(samplerates)}")
    if not analyzer.id3v2 and not analyzer.id3v1:
        findings.append("Sem tags ID3v1/ID3v2")
    if not analyzer.frames:
        findings.append("Nenhum frame MP3 válido encontrado")
    return findings


def run_mp3_parser_job(evidence_path: str, parameters: dict[str, Any] | None = None) -> dict[str, Any]:
    from forensics.audio.mp3_parser import MP3Analyzer

    params = parameters or {}
    out_dir = job_artifact_dir(params, fallback_subdir="mp3_parser")
    analyzer = MP3Analyzer(evidence_path)
    report = analyzer.analyze()

    frames = analyzer.frames or []
    bitrates = sorted({f.bitrate for f in frames})
    samplerates = sorted({f.samplerate for f in frames})
    encoder = _mp3_encoder(analyzer)
    findings = _mp3_findings(analyzer)

    summary = {
        "adapter": "mp3_parser",
        "filepath": analyzer.filepath,
        "filesize": analyzer.filesize,
        "frame_count": len(frames),
        "frames_sample": [_safe_json(f) for f in frames[:32]],
        "bitrates_kbps": bitrates,
        "samplerates_hz": samplerates,
        "id3v1": _safe_json(analyzer.id3v1),
        "id3v2": _safe_json(analyzer.id3v2),
        "vbr_header": _safe_json(analyzer.vbr_header),
        "encoder": encoder,
        "findings": findings,
        "audio_start": analyzer.audio_start,
        "audio_end": analyzer.audio_end,
    }
    paths = _write_artifacts(out_dir, report=report, summary=summary)

    return {
        "success": True,
        "adapter": "mp3_parser",
        "status": "completed",
        "report": report,
        "frame_count": len(frames),
        "frames_sample": summary["frames_sample"],
        "bitrates_kbps": bitrates,
        "samplerates_hz": samplerates,
        "id3v1": summary["id3v1"],
        "id3v2": summary["id3v2"],
        "vbr_header": summary["vbr_header"],
        "encoder": encoder,
        "findings": findings,
        **paths,
    }


def _opus_page_summary(page: Any) -> dict[str, Any]:
    return {
        "offset": page.offset,
        "version": page.version,
        "header_type": page.header_type,
        "granule_position": page.granule_position,
        "serial_number": page.serial_number,
        "page_sequence": page.page_sequence,
        "checksum": page.checksum,
        "segment_count": len(page.segments),
        "data_length": len(page.data),
        "is_bos": page.is_bos,
        "is_eos": page.is_eos,
        "is_continued": page.is_continued,
    }


def _opus_toc_summary(toc: Any) -> dict[str, Any]:
    return {
        "toc_value": toc.toc_value,
        "config": toc.config,
        "stereo": toc.stereo,
        "frame_count_code": toc.frame_count_code,
        "mode": toc.get_mode(),
        "bandwidth": toc.get_bandwidth(),
        "frame_count": toc.get_frame_count(),
    }


def run_opus_parser_job(evidence_path: str, parameters: dict[str, Any] | None = None) -> dict[str, Any]:
    from forensics.audio.opus_parser import OggOpusAnalyzer

    params = parameters or {}
    out_dir = job_artifact_dir(params, fallback_subdir="opus_parser")
    analyzer = OggOpusAnalyzer(evidence_path)
    report = analyzer.analyze()

    if report.startswith("ERRO"):
        return {
            "success": False,
            "error": report,
            "adapter": "opus_parser",
            "errors": list(analyzer.errors),
            "warnings": list(analyzer.warnings),
        }

    origin = analyzer.identify_origin()
    serial = analyzer.analyze_serial_number()
    pages = analyzer.pages or []
    toc = analyzer.toc_analysis or []

    summary = {
        "adapter": "opus_parser",
        "filepath": analyzer.filepath,
        "filesize": analyzer.filesize,
        "page_count": len(pages),
        "pages_sample": [_opus_page_summary(p) for p in pages[:64]],
        "id_header": _safe_json(analyzer.id_header),
        "comment_header": _safe_json(analyzer.comment_header),
        "origin": _safe_json(origin),
        "serial_number": _safe_json(serial),
        "duration_seconds": analyzer.duration_seconds,
        "toc_count": len(toc),
        "toc_sample": [_opus_toc_summary(t) for t in toc[:64]],
        "errors": list(analyzer.errors),
        "warnings": list(analyzer.warnings),
        "platform_hint": origin.get("platform_hint") or serial.get("platform_signature") or "Desconhecido",
    }
    paths = _write_artifacts(out_dir, report=report, summary=summary)

    return {
        "success": True,
        "adapter": "opus_parser",
        "status": "completed",
        "report": report,
        "page_count": len(pages),
        "pages_sample": summary["pages_sample"],
        "id_header": summary["id_header"],
        "comment_header": summary["comment_header"],
        "origin": summary["origin"],
        "serial_number": summary["serial_number"],
        "duration_seconds": analyzer.duration_seconds,
        "toc_count": len(toc),
        "toc_sample": summary["toc_sample"],
        "errors": summary["errors"],
        "warnings": summary["warnings"],
        "platform_hint": summary["platform_hint"],
        **paths,
    }
