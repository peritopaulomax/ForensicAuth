"""Comparação posicional de estruturas JPEG (referência vs candidatos)."""

from __future__ import annotations

from typing import Any

from core.metadata.jpeg_structure_dump import dump_jpeg_structure


def _dqt_tables_equal(a: list[dict[str, Any]] | None, b: list[dict[str, Any]] | None) -> bool:
    if not a and not b:
        return True
    if not a or not b:
        return False
    if len(a) != len(b):
        return False

    def norm(t: dict[str, Any]) -> tuple:
        return (t.get("table_id"), t.get("precision"), tuple(t.get("matrix") or []))

    return sorted(norm(t) for t in a) == sorted(norm(t) for t in b)


def _thumbnail_structures_equal(
    ref_thumb: dict[str, Any] | None,
    cand_thumb: dict[str, Any] | None,
) -> bool:
    if not ref_thumb and not cand_thumb:
        return True
    if not ref_thumb or not cand_thumb:
        return False
    ref_markers = ref_thumb.get("markers") or []
    cand_markers = cand_thumb.get("markers") or []
    return _compare_marker_lists(ref_markers, cand_markers)["fully_matches"]


def _compare_single_markers(
    ref_m: dict[str, Any] | None,
    cand_m: dict[str, Any] | None,
) -> tuple[str, str | None]:
    """Retorna (status, reason). status: match | diverge | missing | extra."""
    if ref_m is None and cand_m is None:
        return "match", None
    if ref_m is None:
        return "extra", "marcador extra no candidato"
    if cand_m is None:
        return "missing", "marcador ausente no candidato"

    ref_name = ref_m.get("name", "")
    cand_name = cand_m.get("name", "")
    if ref_name != cand_name:
        return "diverge", f"tipo divergente ({cand_name} vs {ref_name})"

    if ref_name == "DQT":
        if not _dqt_tables_equal(ref_m.get("dqt_tables"), cand_m.get("dqt_tables")):
            return "diverge", "matriz de quantização DQT diferente"
        return "match", None

    # DHT: apenas presença/tipo na posição — conteúdo Huffman é adaptativo por codificador.

    if ref_name.startswith("APP"):
        ref_has = bool(ref_m.get("has_thumbnail"))
        cand_has = bool(cand_m.get("has_thumbnail"))
        if ref_has and cand_has:
            if not _thumbnail_structures_equal(ref_m.get("thumbnail"), cand_m.get("thumbnail")):
                return "diverge", "estrutura do thumbnail APP diferente"
            return "match", None
        if ref_has != cand_has:
            return "diverge", "presença de thumbnail APP divergente"
        return "match", None

    return "match", None


def _marker_cell(ref_m: dict[str, Any] | None, cand_m: dict[str, Any] | None) -> dict[str, Any]:
    status, reason = _compare_single_markers(ref_m, cand_m)
    display = (cand_m or ref_m or {}).get("display_name") or (cand_m or ref_m or {}).get("name") or "—"
    has_thumb = bool((cand_m or ref_m or {}).get("has_thumbnail"))
    return {
        "status": status,
        "reason": reason,
        "display_name": display,
        "reference_name": ref_m.get("name") if ref_m else None,
        "candidate_name": cand_m.get("name") if cand_m else None,
        "has_thumbnail": has_thumb,
    }


def _slim_marker_for_client(marker: dict[str, Any]) -> dict[str, Any]:
    """Mantém só campos necessários à UI (evita payload gigante)."""
    name = marker.get("name") or ""
    out: dict[str, Any] = {
        "name": name,
        "display_name": marker.get("display_name") or name,
        "has_thumbnail": bool(marker.get("has_thumbnail")),
    }
    if name == "DQT":
        out["dqt_tables"] = marker.get("dqt_tables") or []
    thumb = marker.get("thumbnail")
    if out["has_thumbnail"] and isinstance(thumb, dict):
        out["thumbnail"] = {
            "summary": thumb.get("summary"),
            "markers": [
                _slim_marker_for_client(tm)
                for tm in (thumb.get("markers") or [])
                if isinstance(tm, dict)
            ],
        }
    return out


def _slim_structure_for_client(dump: dict[str, Any]) -> dict[str, Any]:
    """Remove campos redundantes/pesados antes de enviar ao frontend."""
    markers = dump.get("comparison_markers") or []
    return {
        "available": dump.get("available"),
        "reason": dump.get("reason"),
        "evidence_id": dump.get("evidence_id"),
        "label": dump.get("label"),
        "filename": dump.get("filename"),
        "comparison_marker_count": dump.get("comparison_marker_count"),
        "comparison_markers": [
            _slim_marker_for_client(m) for m in markers if isinstance(m, dict)
        ],
        "summary": dump.get("summary"),
    }


def _compare_marker_lists(
    ref_markers: list[dict[str, Any]],
    cand_markers: list[dict[str, Any]],
) -> dict[str, Any]:
    max_len = max(len(ref_markers), len(cand_markers))
    cells: list[dict[str, Any]] = []
    all_match = True

    for i in range(max_len):
        ref_m = ref_markers[i] if i < len(ref_markers) else None
        cand_m = cand_markers[i] if i < len(cand_markers) else None
        cell = _marker_cell(ref_m, cand_m)
        cell["position"] = i
        cells.append(cell)
        if cell["status"] != "match":
            all_match = False

    return {
        "fully_matches": all_match,
        "cells": cells,
        "reference_marker_count": len(ref_markers),
        "candidate_marker_count": len(cand_markers),
    }


def compare_jpeg_structures(
    reference: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    """Compara estrutura do candidato contra a referência."""
    ref_markers = reference.get("comparison_markers") or []
    cand_markers = candidate.get("comparison_markers") or []
    result = _compare_marker_lists(ref_markers, cand_markers)
    result["reference_filename"] = reference.get("filename")
    result["candidate_filename"] = candidate.get("filename")
    return result


def build_comparison_report(
    paths: list[str],
    labels: list[str],
    evidence_ids: list[str],
    *,
    reference_index: int = 0,
) -> dict[str, Any]:
    """Extrai estruturas e compara todas contra a referência."""
    structures: list[dict[str, Any]] = []
    errors: list[str] = []

    for idx, path in enumerate(paths):
        label = labels[idx] if idx < len(labels) else path
        ev_id = evidence_ids[idx] if idx < len(evidence_ids) else ""
        dump = dump_jpeg_structure(path)
        dump["label"] = label
        dump["evidence_id"] = ev_id
        if not dump.get("available"):
            errors.append(f"{label}: {dump.get('reason', 'falha')}")
        structures.append(dump)

    if not structures:
        return {"success": False, "error": "Nenhum arquivo informado"}

    ref_idx = max(0, min(reference_index, len(structures) - 1))
    reference = structures[ref_idx]

    if not reference.get("available"):
        return {
            "success": False,
            "error": f"Referência ({reference.get('label')}) não pôde ser lida: {reference.get('reason')}",
            "structures": structures,
        }

    comparisons: list[dict[str, Any]] = []
    for idx, struct in enumerate(structures):
        if idx == ref_idx:
            comparisons.append(
                {
                    "is_reference": True,
                    "evidence_id": struct.get("evidence_id"),
                    "label": struct.get("label"),
                    "filename": struct.get("filename"),
                    "fully_matches": True,
                    "cells": [
                        {
                            "position": i,
                            "status": "reference",
                            "display_name": m.get("display_name") or m.get("name"),
                            "has_thumbnail": bool(m.get("has_thumbnail")),
                        }
                        for i, m in enumerate(reference.get("comparison_markers") or [])
                    ],
                }
            )
            continue

        if not struct.get("available"):
            comparisons.append(
                {
                    "is_reference": False,
                    "evidence_id": struct.get("evidence_id"),
                    "label": struct.get("label"),
                    "filename": struct.get("filename"),
                    "fully_matches": False,
                    "unavailable": True,
                    "reason": struct.get("reason"),
                    "cells": [],
                }
            )
            continue

        cmp_result = compare_jpeg_structures(reference, struct)
        comparisons.append(
            {
                "is_reference": False,
                "evidence_id": struct.get("evidence_id"),
                "label": struct.get("label"),
                "filename": struct.get("filename"),
                "fully_matches": cmp_result["fully_matches"],
                "cells": cmp_result["cells"],
            }
        )

    max_positions = max(
        (len(c.get("cells") or []) for c in comparisons),
        default=0,
    )

    return {
        "success": True,
        "reference_index": ref_idx,
        "reference_evidence_id": reference.get("evidence_id"),
        "reference_label": reference.get("label"),
        "file_count": len(structures),
        "max_positions": max_positions,
        "structures": [_slim_structure_for_client(s) for s in structures],
        "comparisons": comparisons,
        "errors": errors,
        "all_match": all(
            c.get("fully_matches")
            for c in comparisons
            if not c.get("is_reference") and not c.get("unavailable")
        ),
    }


def _first_divergence_reason(cells: list[dict[str, Any]]) -> str | None:
    for cell in cells:
        if cell.get("status") not in ("match", "reference"):
            reason = cell.get("reason")
            if isinstance(reason, str) and reason.strip():
                return reason
            display = cell.get("display_name") or cell.get("reference_name") or "?"
            return f"divergência em {display}"
    return None


def _dump_structure_for_matrix(
    path: str,
    label: str,
    evidence_id: str,
    errors: list[str],
) -> dict[str, Any]:
    dump = dump_jpeg_structure(path)
    dump["label"] = label
    dump["evidence_id"] = evidence_id
    if not dump.get("available"):
        errors.append(f"{label}: {dump.get('reason', 'falha')}")
    return dump


def build_similarity_matrix(
    *,
    mode: str,
    questioned_paths: list[str],
    questioned_labels: list[str],
    questioned_ids: list[str],
    reference_paths: list[str] | None = None,
    reference_labels: list[str] | None = None,
    reference_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Matriz verde/vermelha: match estrutural (marcadores, DQT, thumbnails APP; DHT só posição/tipo)."""
    if mode not in ("with_reference", "all_pairs"):
        return {"success": False, "error": f"Modo de matriz inválido: {mode}"}

    errors: list[str] = []
    q_structures: list[dict[str, Any]] = []
    for idx, path in enumerate(questioned_paths):
        label = questioned_labels[idx] if idx < len(questioned_labels) else path
        ev_id = questioned_ids[idx] if idx < len(questioned_ids) else ""
        q_structures.append(_dump_structure_for_matrix(path, label, ev_id, errors))

    if mode == "all_pairs":
        if len(q_structures) < 2:
            return {"success": False, "error": "Modo sem referência exige ao menos 2 questionados"}
        row_labels = [s.get("label") or s.get("filename") or "?" for s in q_structures]
        col_labels = list(row_labels)
        rows: list[dict[str, Any]] = []
        for i, ref_struct in enumerate(q_structures):
            cells: list[dict[str, Any]] = []
            for j, cand_struct in enumerate(q_structures):
                if not ref_struct.get("available") or not cand_struct.get("available"):
                    cells.append(
                        {
                            "col_index": j,
                            "matches": False,
                            "unavailable": True,
                            "reason": ref_struct.get("reason") or cand_struct.get("reason"),
                            "questioned_evidence_id": cand_struct.get("evidence_id"),
                            "questioned_label": col_labels[j],
                        }
                    )
                    continue
                if i == j:
                    cells.append(
                        {
                            "col_index": j,
                            "matches": True,
                            "reason": None,
                            "questioned_evidence_id": cand_struct.get("evidence_id"),
                            "questioned_label": col_labels[j],
                        }
                    )
                    continue
                cmp_result = compare_jpeg_structures(ref_struct, cand_struct)
                cells.append(
                    {
                        "col_index": j,
                        "matches": bool(cmp_result.get("fully_matches")),
                        "reason": _first_divergence_reason(cmp_result.get("cells") or []),
                        "questioned_evidence_id": cand_struct.get("evidence_id"),
                        "questioned_label": col_labels[j],
                    }
                )
            rows.append(
                {
                    "row_index": i,
                    "evidence_id": ref_struct.get("evidence_id"),
                    "label": row_labels[i],
                    "cells": cells,
                }
            )
        return {
            "success": True,
            "mode": mode,
            "reference_count": 0,
            "questioned_count": len(q_structures),
            "matrix": {
                "row_labels": row_labels,
                "col_labels": col_labels,
                "rows": rows,
            },
            "questioned_structures": [_slim_structure_for_client(s) for s in q_structures],
            "reference_structures": [],
            "errors": errors,
        }

    ref_paths = reference_paths or []
    ref_labels = reference_labels or []
    ref_ids = reference_ids or []
    if not ref_paths:
        return {"success": False, "error": "Nenhuma referência informada"}

    ref_structures: list[dict[str, Any]] = []
    for idx, path in enumerate(ref_paths):
        label = ref_labels[idx] if idx < len(ref_labels) else path
        ev_id = ref_ids[idx] if idx < len(ref_ids) else ""
        ref_structures.append(_dump_structure_for_matrix(path, label, ev_id, errors))

    row_labels = [s.get("label") or s.get("filename") or "?" for s in ref_structures]
    col_labels = [s.get("label") or s.get("filename") or "?" for s in q_structures]
    rows = []
    for i, ref_struct in enumerate(ref_structures):
        cells = []
        for j, cand_struct in enumerate(q_structures):
            if not ref_struct.get("available") or not cand_struct.get("available"):
                cells.append(
                    {
                        "col_index": j,
                        "matches": False,
                        "unavailable": True,
                        "reason": ref_struct.get("reason") or cand_struct.get("reason"),
                        "questioned_evidence_id": cand_struct.get("evidence_id"),
                        "questioned_label": col_labels[j],
                    }
                )
                continue
            cmp_result = compare_jpeg_structures(ref_struct, cand_struct)
            cells.append(
                {
                    "col_index": j,
                    "matches": bool(cmp_result.get("fully_matches")),
                    "reason": _first_divergence_reason(cmp_result.get("cells") or []),
                    "questioned_evidence_id": cand_struct.get("evidence_id"),
                    "questioned_label": col_labels[j],
                }
            )
        rows.append(
            {
                "row_index": i,
                "evidence_id": ref_struct.get("evidence_id"),
                "label": row_labels[i],
                "cells": cells,
            }
        )

    return {
        "success": True,
        "mode": mode,
        "reference_count": len(ref_structures),
        "questioned_count": len(q_structures),
        "matrix": {
            "row_labels": row_labels,
            "col_labels": col_labels,
            "rows": rows,
        },
        "reference_structures": [_slim_structure_for_client(s) for s in ref_structures],
        "questioned_structures": [_slim_structure_for_client(s) for s in q_structures],
        "errors": errors,
    }


def build_positional_grid_report(
    *,
    mode: str,
    reference_structures: list[dict[str, Any]],
    questioned_structures: list[dict[str, Any]],
    active_reference_evidence_id: str | None = None,
) -> dict[str, Any]:
    """Grade posicional (referência ativa × questionados) para exportação em derivados."""
    if mode == "with_reference":
        if not reference_structures:
            return {"success": False, "error": "Nenhuma referência para grade posicional"}
        active = next(
            (s for s in reference_structures if s.get("evidence_id") == active_reference_evidence_id),
            reference_structures[0],
        )
        ref_markers = active.get("comparison_markers") or []
        ref_rows: list[dict[str, Any]] = []
        for struct in reference_structures:
            is_active = struct.get("evidence_id") == active.get("evidence_id")
            if not is_active:
                ref_rows.append(
                    {
                        "is_reference": True,
                        "inactive_reference": True,
                        "row_section": "reference",
                        "evidence_id": struct.get("evidence_id"),
                        "label": struct.get("label"),
                        "filename": struct.get("filename"),
                        "fully_matches": True,
                        "cells": [],
                    }
                )
                continue
            if not struct.get("available"):
                ref_rows.append(
                    {
                        "is_reference": True,
                        "row_section": "reference",
                        "evidence_id": struct.get("evidence_id"),
                        "label": struct.get("label"),
                        "filename": struct.get("filename"),
                        "fully_matches": False,
                        "unavailable": True,
                        "reason": struct.get("reason"),
                        "cells": [],
                    }
                )
                continue
            ref_rows.append(
                {
                    "is_reference": True,
                    "row_section": "reference",
                    "evidence_id": struct.get("evidence_id"),
                    "label": struct.get("label"),
                    "filename": struct.get("filename"),
                    "fully_matches": True,
                    "cells": [
                        {
                            "position": i,
                            "status": "reference",
                            "display_name": m.get("display_name") or m.get("name"),
                            "has_thumbnail": bool(m.get("has_thumbnail")),
                        }
                        for i, m in enumerate(ref_markers)
                    ],
                }
            )

        questioned_rows: list[dict[str, Any]] = []
        for struct in questioned_structures:
            if not struct.get("available"):
                questioned_rows.append(
                    {
                        "is_reference": False,
                        "row_section": "questioned",
                        "evidence_id": struct.get("evidence_id"),
                        "label": struct.get("label"),
                        "filename": struct.get("filename"),
                        "fully_matches": False,
                        "unavailable": True,
                        "reason": struct.get("reason"),
                        "cells": [],
                    }
                )
                continue
            cmp_result = compare_jpeg_structures(active, struct)
            questioned_rows.append(
                {
                    "is_reference": False,
                    "row_section": "questioned",
                    "evidence_id": struct.get("evidence_id"),
                    "label": struct.get("label"),
                    "filename": struct.get("filename"),
                    "fully_matches": cmp_result["fully_matches"],
                    "cells": cmp_result["cells"],
                }
            )

        comparisons = ref_rows + questioned_rows
        structures = list(reference_structures) + list(questioned_structures)
        active_id = active.get("evidence_id")
        active_label = active.get("label")
    elif mode == "all_pairs":
        if len(questioned_structures) < 1:
            return {"success": False, "error": "Nenhum questionado para grade posicional"}
        ref_idx = 0
        reference = questioned_structures[ref_idx]
        ref_markers = reference.get("comparison_markers") or []
        comparisons = []
        for idx, struct in enumerate(questioned_structures):
            if idx == ref_idx:
                comparisons.append(
                    {
                        "is_reference": True,
                        "evidence_id": struct.get("evidence_id"),
                        "label": struct.get("label"),
                        "filename": struct.get("filename"),
                        "fully_matches": True,
                        "cells": [
                            {
                                "position": i,
                                "status": "reference",
                                "display_name": m.get("display_name") or m.get("name"),
                                "has_thumbnail": bool(m.get("has_thumbnail")),
                            }
                            for i, m in enumerate(ref_markers)
                        ],
                    }
                )
                continue
            if not struct.get("available"):
                comparisons.append(
                    {
                        "is_reference": False,
                        "evidence_id": struct.get("evidence_id"),
                        "label": struct.get("label"),
                        "filename": struct.get("filename"),
                        "fully_matches": False,
                        "unavailable": True,
                        "reason": struct.get("reason"),
                        "cells": [],
                    }
                )
                continue
            cmp_result = compare_jpeg_structures(reference, struct)
            comparisons.append(
                {
                    "is_reference": False,
                    "evidence_id": struct.get("evidence_id"),
                    "label": struct.get("label"),
                    "filename": struct.get("filename"),
                    "fully_matches": cmp_result["fully_matches"],
                    "cells": cmp_result["cells"],
                }
            )
        structures = list(questioned_structures)
        active_id = reference.get("evidence_id")
        active_label = reference.get("label")
    else:
        return {"success": False, "error": f"Modo inválido para grade: {mode}"}

    max_positions = max((len(c.get("cells") or []) for c in comparisons), default=0)
    return {
        "success": True,
        "mode": mode,
        "artifact_kind": "positional_grid",
        "reference_evidence_id": active_id,
        "reference_label": active_label,
        "file_count": len(comparisons),
        "max_positions": max_positions,
        "structures": structures,
        "comparisons": comparisons,
        "all_match": all(
            c.get("fully_matches")
            for c in comparisons
            if not c.get("is_reference") and not c.get("unavailable") and not c.get("inactive_reference")
        ),
    }
