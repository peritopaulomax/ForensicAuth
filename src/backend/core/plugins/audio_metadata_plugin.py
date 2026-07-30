"""Plugin de metadados de audio — ExifTool + probe tecnico + C2PA."""

from __future__ import annotations

import json
from typing import Any, Dict, Tuple

from core.forensic_plugin import ForensicPlugin
from core.job_staging import job_artifact_dir
from core.metadata.audio_extractor import extract_audio_metadata


class AudioMetadataPlugin(ForensicPlugin):
    """Extrai metadados de audio (ID3, Vorbis, RIFF, QuickTime, XMP, C2PA)."""

    @property
    def name(self) -> str:
        return "audio_metadata"

    @property
    def supported_types(self) -> list[str]:
        return ["audio"]

    def validate_parameters(self, parameters: Dict[str, Any]) -> Tuple[bool, str]:
        return True, ""

    def analyze(self, evidence_path: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        result_dir = job_artifact_dir(parameters, fallback_subdir="audio_metadata")
        payload = extract_audio_metadata(evidence_path)
        if not payload.get("success"):
            return payload

        json_path = result_dir / "metadata_report.json"
        with open(json_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)

        lines = [
            "RELATORIO — METADADOS DE AUDIO",
            f"Arquivo: {payload.get('file', {}).get('filename')}",
            f"Motor: {payload.get('summary', {}).get('metadata_engine')}",
            "",
            "RESUMO TECNICO",
        ]
        summary = payload.get("summary") or {}
        for key in (
            "codec",
            "sample_rate_hz",
            "channels",
            "bit_depth",
            "duration_sec",
            "total_tags",
            "has_c2pa",
            "c2pa_validation_state",
        ):
            if summary.get(key) is not None:
                lines.append(f"  {key}: {summary[key]}")
        lines.append("")
        lines.append("DESTAQUES")
        for h in payload.get("highlights") or []:
            lines.append(f"  {h.get('tag')}: {h.get('value')}")
        lines.append("")
        lines.append("FAMILIAS")
        families = (payload.get("metadata") or {}).get("families") or {}
        for fam, entries in families.items():
            lines.append(f"  [{fam}] {len(entries)} tags")

        txt_path = result_dir / "metadata_report.txt"
        txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        payload["metadata_json_path"] = str(json_path)
        payload["metadata_report_path"] = str(txt_path)
        payload["metadata_report_filename"] = "metadata_report.json"

        c2pa = payload.get("c2pa_structured") or {}
        if c2pa.get("available") and c2pa.get("present") and c2pa.get("store") is not None:
            c2pa_path = result_dir / "c2pa_manifest.json"
            artifact = {
                "present": c2pa.get("present"),
                "is_valid": c2pa.get("is_valid"),
                "validation_state": c2pa.get("validation_state"),
                "validation_codes": c2pa.get("validation_codes", []),
                "claim_generator": c2pa.get("claim_generator"),
                "title": c2pa.get("title"),
                "format": c2pa.get("format"),
                "active_manifest": c2pa.get("active_manifest"),
                "actions": c2pa.get("actions", []),
                "signature_info": c2pa.get("signature_info", {}),
                "ingredient_count": c2pa.get("ingredient_count"),
                "manifest_count": c2pa.get("manifest_count"),
                "sdk_version": c2pa.get("sdk_version"),
                "trust_anchors_configured": c2pa.get("trust_anchors_configured"),
                "store": c2pa.get("store"),
            }
            with open(c2pa_path, "w", encoding="utf-8") as fh:
                json.dump(artifact, fh, ensure_ascii=False, indent=2)
            payload["c2pa_manifest_path"] = str(c2pa_path)
            payload["c2pa_manifest_filename"] = "c2pa_manifest.json"

        return payload
