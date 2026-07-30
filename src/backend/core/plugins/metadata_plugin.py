"""Metadata extraction plugin — EXIF, IPTC, XMP, ICC, MakerNotes, Adobe, C2PA, estrutura JPEG."""

from __future__ import annotations

import json
from typing import Any, Dict, Tuple

from core.forensic_plugin import ForensicPlugin
from core.job_staging import job_artifact_dir
from core.metadata.extractor import extract_image_metadata


class MetadataPlugin(ForensicPlugin):
    """Extrai metadados completos, C2PA e estrutura JPEG (quantizacao, Huffman)."""

    @property
    def name(self) -> str:
        return "metadata"

    @property
    def supported_types(self) -> list[str]:
        return ["imagem"]

    def validate_parameters(self, parameters: Dict[str, Any]) -> Tuple[bool, str]:
        return True, ""

    def analyze(self, evidence_path: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        result_dir = job_artifact_dir(parameters, fallback_subdir="metadata")

        payload = extract_image_metadata(evidence_path)
        if not payload.get("success"):
            return payload

        json_path = result_dir / "metadata_report.json"
        with open(json_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)

        payload["metadata_json_path"] = str(json_path)
        payload["metadata_report_filename"] = "metadata_report.json"

        xmp = payload.get("xmp_structured") or {}
        if xmp.get("available") and xmp.get("packet_xml"):
            xmp_xml_path = result_dir / "xmp_packet.xml"
            xmp_xml_path.write_text(xmp["packet_xml"], encoding="utf-8")
            payload["xmp_packet_path"] = str(xmp_xml_path)

            tree_payload = {
                "packet_sha256": xmp.get("packet_sha256"),
                "source": xmp.get("source"),
                "property_count": xmp.get("property_count", 0),
                "structural_tree": xmp.get("structural_tree"),
                "semantic_groups": xmp.get("semantic_groups", []),
                "warnings": xmp.get("warnings", []),
            }
            xmp_tree_path = result_dir / "xmp_tree.json"
            with open(xmp_tree_path, "w", encoding="utf-8") as fh:
                json.dump(tree_payload, fh, ensure_ascii=False, indent=2)
            payload["xmp_tree_json_path"] = str(xmp_tree_path)

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
