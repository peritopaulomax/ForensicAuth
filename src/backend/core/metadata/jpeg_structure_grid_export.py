"""Exportação da grade posicional JPEG: JSON enriquecido e relatório TXT."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.metadata.jpeg_structure_matrix_export import COMPARISON_CRITERIA_VERSION, COMPARISON_RULES

_CONVERGENT_STATUSES = frozenset({"match", "reference"})


def enrich_grid_payload(
    payload: dict[str, Any],
    *,
    reference_evidence_ids: list[str],
    questioned_evidence_ids: list[str],
) -> dict[str, Any]:
    enriched = dict(payload)
    enriched["technique"] = "jpeg_structure_compare"
    enriched["artifact_kind"] = "positional_grid"
    enriched["criteria_version"] = COMPARISON_CRITERIA_VERSION
    enriched["comparison_rules"] = dict(COMPARISON_RULES)
    enriched["reference_evidence_ids"] = list(reference_evidence_ids)
    enriched["questioned_evidence_ids"] = list(questioned_evidence_ids)
    enriched["generated_at"] = datetime.now(timezone.utc).isoformat()
    return enriched


def render_grid_txt(payload: dict[str, Any], output_path: Path) -> None:
    comparisons = payload.get("comparisons") or []
    ref_label = payload.get("reference_label") or "—"
    lines: list[str] = [
        "Comparação de estruturas JPEG — grade posicional",
        f"Modo: {payload.get('mode', '—')}",
        f"Referência ativa: {ref_label} ({payload.get('reference_evidence_id') or '—'})",
        f"Critérios (v{payload.get('criteria_version', COMPARISON_CRITERIA_VERSION)}): "
        "marcadores posicionais, DQT conteúdo, DHT só posição/tipo, thumbnails APP",
        f"Gerado em: {payload.get('generated_at', '—')}",
        "",
    ]

    for row in comparisons:
        if row.get("inactive_reference"):
            continue
        label = row.get("label") or row.get("filename") or "?"
        if row.get("is_reference"):
            lines.append(f"PAD {label}")
            continue
        if row.get("unavailable"):
            lines.append(f"  {label}: indisponível ({row.get('reason') or '?'})")
            continue
        status = "✓ convergente" if row.get("fully_matches") else "✗ divergente"
        lines.append(f"  {label}: {status}")
        for cell in row.get("cells") or []:
            st = cell.get("status")
            if st in _CONVERGENT_STATUSES:
                continue
            pos = cell.get("display_name") or cell.get("position")
            reason = cell.get("reason") or st
            lines.append(f"    · {pos}: {reason}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
