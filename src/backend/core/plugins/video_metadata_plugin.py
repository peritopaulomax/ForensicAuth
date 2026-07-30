"""Plugin de metadados profundos de video — ExifTool + ffprobe + ISO BMFF."""

from __future__ import annotations

import json
from typing import Any, Dict, Tuple

from core.forensic_plugin import ForensicPlugin
from core.job_staging import job_artifact_dir
from core.metadata.video_extractor import extract_video_metadata


class VideoMetadataPlugin(ForensicPlugin):
    """Extrai metadados profundos de video (tags, streams, GPS, camera, container)."""

    @property
    def name(self) -> str:
        return "video_metadata"

    @property
    def supported_types(self) -> list[str]:
        return ["video"]

    def validate_parameters(self, parameters: Dict[str, Any]) -> Tuple[bool, str]:
        return True, ""

    def analyze(self, evidence_path: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        result_dir = job_artifact_dir(parameters, fallback_subdir="video_metadata")
        payload = extract_video_metadata(evidence_path)
        if not payload.get("success"):
            return payload

        json_path = result_dir / "metadata_report.json"
        with open(json_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)

        summary = payload.get("summary") or {}
        file_info = payload.get("file") or {}
        lines = [
            "RELATORIO — METADADOS PROFUNDOS DE VIDEO",
            f"Arquivo: {file_info.get('filename')}",
            f"Tamanho: {file_info.get('size_bytes')} bytes",
            f"Motor: {summary.get('metadata_engine')}",
            "",
            "RESUMO",
            f"  format: {summary.get('format_name')}",
            f"  codec: {summary.get('codec_name')}",
            f"  resolucao: {summary.get('width')}x{summary.get('height')}",
            f"  duracao_s: {summary.get('duration_sec')}",
            f"  bitrate: {summary.get('bit_rate')}",
            f"  total_tags: {summary.get('total_tags')}",
            f"  gps: {summary.get('has_gps')}",
            f"  camera: {summary.get('has_camera')}",
            "",
            "DESTAQUES",
        ]
        for h in payload.get("highlights") or []:
            lines.append(f"  {h.get('tag')}: {h.get('value')}")
        lines.append("")
        lines.append("FAMILIAS")
        families = (payload.get("metadata") or {}).get("families") or {}
        for fam, entries in families.items():
            lines.append(f"  [{fam}] {len(entries)} tags")
        lines.append("")
        lines.append("INSIGHTS")
        for insight in payload.get("forensic_insights") or []:
            lines.append(
                f"  [{insight.get('severity')}] {insight.get('title')}: {insight.get('detail')}"
            )

        txt_path = result_dir / "metadata_report.txt"
        txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        payload["metadata_json_path"] = str(json_path)
        payload["metadata_report_path"] = str(txt_path)
        payload["metadata_report_filename"] = "metadata_report.json"
        return payload
