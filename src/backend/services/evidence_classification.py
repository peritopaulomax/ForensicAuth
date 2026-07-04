"""Classify evidence records: case evidences vs references vs derivatives."""

from __future__ import annotations

from typing import Any, Dict, Optional

from models.evidence import Evidence

TECHNIQUE_LABELS = {
    "prnu": "PRNU",
    "dct_quantization": "DCT",
    "metadata": "Metadados",
    "pdf_structure_similarity": "PDF estrutura",
    "isomedia_compare": "Video ISO BMFF",
    "jpeg_structure_compare": "JPEG estrutura",
}


def evidence_metadata(evidence: Evidence) -> Dict[str, Any]:
    return evidence.extra_metadata or {}


def is_derived(evidence: Evidence) -> bool:
    return evidence_metadata(evidence).get("origin") == "derived"


def is_reference(evidence: Evidence) -> bool:
    meta = evidence_metadata(evidence)
    if meta.get("is_reference"):
        return True
    if meta.get("prnu_reference"):
        return True
    if meta.get("reference"):
        return True
    return False


def is_case_evidence(evidence: Evidence) -> bool:
    """Original uploads that are neither derived nor technique references."""
    if is_derived(evidence):
        return False
    if is_reference(evidence):
        return False
    return True


def reference_scope(evidence: Evidence) -> str:
    """Return 'global' for user-uploaded global references, 'plugin' otherwise."""
    meta = evidence_metadata(evidence)
    return str(meta.get("reference_scope", "plugin")).lower()


def is_global_reference(evidence: Evidence) -> bool:
    return is_reference(evidence) and reference_scope(evidence) == "global"


def is_plugin_reference(evidence: Evidence) -> bool:
    return is_reference(evidence) and reference_scope(evidence) != "global"


def reference_type(evidence: Evidence) -> Optional[str]:
    meta = evidence_metadata(evidence)
    return meta.get("reference_type")


def reference_technique(evidence: Evidence) -> Optional[str]:
    meta = evidence_metadata(evidence)
    return meta.get("reference_technique") or meta.get("for_technique")


def reference_group_label(evidence: Evidence) -> str:
    meta = evidence_metadata(evidence)
    label = meta.get("reference_group_label")
    if label and str(label).strip():
        return str(label).strip()
    if meta.get("prnu_reference"):
        return "Sem rotulo"
    if meta.get("reference"):
        return "Padrao"
    return "Sem rotulo"


def reference_display_label(technique: str, group_label: str) -> str:
    tech = TECHNIQUE_LABELS.get(technique, technique.upper() if technique else "REF")
    return f"{tech} - {group_label}"


def group_references(evidences: list[Evidence]) -> list[dict]:
    """Group plugin reference evidences by technique + rotulo."""
    buckets: dict[tuple[str, str], list[Evidence]] = {}
    for ev in evidences:
        if not is_reference(ev) or is_global_reference(ev):
            continue
        tech = reference_technique(ev) or "unknown"
        label = reference_group_label(ev)
        key = (tech, label)
        buckets.setdefault(key, []).append(ev)

    groups = []
    for (tech, label), items in sorted(buckets.items(), key=lambda x: (x[0][0], x[0][1])):
        groups.append(
            {
                "technique": tech,
                "group_label": label,
                "display_label": reference_display_label(tech, label),
                "evidences": sorted(items, key=lambda e: e.created_at or "", reverse=True),
            }
        )
    return groups


def group_global_references(evidences: list[Evidence]) -> list[dict]:
    """Group global reference evidences by reference_type + rotulo."""
    buckets: dict[tuple[str, str], list[Evidence]] = {}
    for ev in evidences:
        if not is_global_reference(ev):
            continue
        ref_type = reference_type(ev) or ev.file_type or "unknown"
        label = reference_group_label(ev)
        key = (ref_type, label)
        buckets.setdefault(key, []).append(ev)

    groups = []
    for (ref_type, label), items in sorted(buckets.items(), key=lambda x: (x[0][0], x[0][1])):
        display = f"{label} ({ref_type.upper()})"
        groups.append(
            {
                "reference_type": ref_type,
                "group_label": label,
                "display_label": display,
                "evidences": sorted(items, key=lambda e: e.created_at or "", reverse=True),
            }
        )
    return groups
