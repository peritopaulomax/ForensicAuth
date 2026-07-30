"""Central overrides for evidence-role resolution per technique.

Ideally each ForensicPlugin declares x-forensic-role in parameters_schema.
This module provides a migration bridge for legacy plugins that have not yet
been updated, so the orchestration layer can resolve evidence IDs generically.
"""

from __future__ import annotations

from typing import Any


def _schema(properties: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "properties": properties}


EVIDENCE_ROLE_OVERRIDES: dict[str, dict[str, Any]] = {
    "dct_quantization": _schema({
        "reference_evidence_id": {
            "type": "string",
            "format": "uuid",
            "x-forensic-role": "reference",
            "x-forensic-media": "imagem",
        }
    }),
    "prnu": _schema({
        "fingerprint_id": {
            "type": "string",
            "x-forensic-role": "fingerprint",
        }
    }),
    "jpeg_structure_compare": _schema({
        "questioned_evidence_ids": {
            "type": "array",
            "items": {"type": "string", "format": "uuid"},
            "x-forensic-role": "questioned",
            "x-forensic-media": "imagem",
            "x-forensic-multiple": True,
        },
        "reference_evidence_ids": {
            "type": "array",
            "items": {"type": "string", "format": "uuid"},
            "x-forensic-role": "reference",
            "x-forensic-media": "imagem",
            "x-forensic-multiple": True,
        },
        "evidence_ids": {
            "type": "array",
            "items": {"type": "string", "format": "uuid"},
            "x-forensic-role": "questioned",
            "x-forensic-media": "imagem",
            "x-forensic-multiple": True,
        },
    }),
    "pdf_structure_similarity": _schema({
        "questioned_evidence_ids": {
            "type": "array",
            "items": {"type": "string", "format": "uuid"},
            "x-forensic-role": "questioned",
            "x-forensic-media": "pdf",
            "x-forensic-multiple": True,
        },
        "reference_evidence_ids": {
            "type": "array",
            "items": {"type": "string", "format": "uuid"},
            "x-forensic-role": "reference",
            "x-forensic-media": "pdf",
            "x-forensic-multiple": True,
        },
    }),
    "isomedia_compare": _schema({
        "questioned_evidence_ids": {
            "type": "array",
            "items": {"type": "string", "format": "uuid"},
            "x-forensic-role": "questioned",
            "x-forensic-media": "video",
            "x-forensic-multiple": True,
        },
        "reference_evidence_ids": {
            "type": "array",
            "items": {"type": "string", "format": "uuid"},
            "x-forensic-role": "reference",
            "x-forensic-media": "video",
            "x-forensic-multiple": True,
        },
    }),
}


def resolve_evidence_schema(
    technique: str,
    plugin_schema: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Return effective parameters schema for evidence-role resolution.

    Plugin schema takes precedence; overrides fill gaps for legacy plugins.
    """
    override = EVIDENCE_ROLE_OVERRIDES.get(technique)
    if not plugin_schema:
        return override
    if not override:
        return plugin_schema

    merged_properties = dict(plugin_schema.get("properties") or {})
    for name, prop in override.get("properties", {}).items():
        if name not in merged_properties:
            merged_properties[name] = prop
        elif "x-forensic-role" in prop:
            merged_properties[name] = {**merged_properties[name], **prop}

    return {**plugin_schema, "properties": merged_properties}
