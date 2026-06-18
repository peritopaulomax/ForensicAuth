"""Exportação de matriz JPEG estrutural: JSON enriquecido, PNG e relatório TXT."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import ListedColormap

COMPARISON_CRITERIA_VERSION = "2026-06"

COMPARISON_RULES = {
    "markers": "positional_type",
    "dqt": "content",
    "dht": "position_only",
    "app_thumbnail": "structure",
}


def _alias_for(role: str, index: int) -> str:
    prefix = "R" if role == "reference" else "Q"
    return f"{prefix}{index + 1}"


def build_matrix_legend(payload: dict[str, Any]) -> dict[str, str]:
    """Mapa alias → rótulo de arquivo."""
    legend: dict[str, str] = {}
    matrix = payload.get("matrix") or {}
    mode = payload.get("mode", "all_pairs")
    row_labels = matrix.get("row_labels") or []
    col_labels = matrix.get("col_labels") or []
    rows = matrix.get("rows") or []

    if mode == "with_reference":
        for i, label in enumerate(row_labels):
            legend[_alias_for("reference", i)] = str(label)
        for i, label in enumerate(col_labels):
            legend[_alias_for("questioned", i)] = str(label)
    else:
        for i, label in enumerate(row_labels):
            alias = _alias_for("questioned", i)
            if alias not in legend:
                legend[alias] = str(label)
    return legend


def enrich_matrix_payload(
    payload: dict[str, Any],
    *,
    reference_evidence_ids: list[str],
    questioned_evidence_ids: list[str],
) -> dict[str, Any]:
    """Acrescenta metadados de auditoria ao payload da matriz."""
    enriched = dict(payload)
    enriched["technique"] = "jpeg_structure_compare"
    enriched["criteria_version"] = COMPARISON_CRITERIA_VERSION
    enriched["comparison_rules"] = dict(COMPARISON_RULES)
    enriched["reference_evidence_ids"] = list(reference_evidence_ids)
    enriched["questioned_evidence_ids"] = list(questioned_evidence_ids)
    enriched["legend"] = build_matrix_legend(payload)
    enriched["generated_at"] = datetime.now(timezone.utc).isoformat()
    return enriched


def _matrix_to_grid(payload: dict[str, Any]) -> tuple[np.ndarray, list[str], list[str], str]:
    """Retorna (grid, row_aliases, col_aliases, title_suffix). Valores: 1 match, 0 diverge, -1 indisponível."""
    matrix = payload.get("matrix") or {}
    mode = payload.get("mode", "all_pairs")
    rows = matrix.get("rows") or []
    col_labels = matrix.get("col_labels") or []
    n_rows = len(rows)
    n_cols = len(col_labels)
    grid = np.full((n_rows, n_cols), np.nan, dtype=float)

    if mode == "with_reference":
        row_aliases = [_alias_for("reference", i) for i in range(n_rows)]
        col_aliases = [_alias_for("questioned", i) for i in range(n_cols)]
        title_suffix = "padrões × questionados"
    else:
        row_aliases = [_alias_for("questioned", i) for i in range(n_rows)]
        col_aliases = [_alias_for("questioned", i) for i in range(n_cols)]
        title_suffix = "questionados × questionados"

    for i, row in enumerate(rows):
        for cell in row.get("cells") or []:
            j = int(cell.get("col_index", 0))
            if cell.get("unavailable"):
                grid[i, j] = -1
            elif cell.get("matches"):
                grid[i, j] = 1
            else:
                grid[i, j] = 0
    return grid, row_aliases, col_aliases, title_suffix


_COLOR_DIVERGE = "#fecaca"
_COLOR_MATCH = "#bbf7d0"
_EDGE_DIVERGE = "#f87171"
_EDGE_MATCH = "#4ade80"


def _draw_matrix_color_legend(fig) -> None:
    """Legenda visual alinhada às células da matriz (cor + símbolo)."""
    leg = fig.add_axes((0.52, 0.01, 0.46, 0.07))
    leg.set_xlim(0, 1)
    leg.set_ylim(0, 1)
    leg.axis("off")

    items = (
        (_COLOR_MATCH, _EDGE_MATCH, "v", "convergente"),
        (_COLOR_DIVERGE, _EDGE_DIVERGE, "x", "divergente"),
    )
    for idx, (face, edge, sym, label) in enumerate(items):
        x0 = idx * 0.52
        leg.add_patch(
            plt.Rectangle(
                (x0, 0.18),
                0.1,
                0.64,
                facecolor=face,
                edgecolor=edge,
                linewidth=0.6,
            )
        )
        leg.text(x0 + 0.05, 0.5, sym, ha="center", va="center", fontsize=9, fontweight="bold", color="#111827")
        leg.text(x0 + 0.13, 0.5, label, ha="left", va="center", fontsize=8, color="#374151")


def render_matrix_png(payload: dict[str, Any], output_path: Path) -> None:
    """Gera heatmap compacto ✓/✗ (verde convergente / vermelho divergente)."""
    grid, row_aliases, col_aliases, title_suffix = _matrix_to_grid(payload)
    n_rows, n_cols = grid.shape
    if n_rows == 0 or n_cols == 0:
        output_path.write_bytes(b"")
        return

    # 0 = divergente, 1 = convergente (indisponível conta como divergente)
    cmap = ListedColormap([_COLOR_DIVERGE, _COLOR_MATCH])
    norm_grid = np.where(np.isnan(grid), 0, np.where(grid >= 1, 1, 0))

    cell_w = max(0.25, min(0.45, 12 / max(n_cols, 1)))
    cell_h = max(0.25, min(0.45, 10 / max(n_rows, 1)))
    fig_w = min(8, max(4, n_cols * cell_w + 1.6))
    fig_h = min(7, max(3.2, n_rows * cell_h + 1.4))

    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    ax.imshow(norm_grid, cmap=cmap, vmin=0, vmax=1, aspect="auto")

    ax.set_xticks(range(n_cols))
    ax.set_yticks(range(n_rows))
    ax.set_xticklabels(col_aliases, fontsize=max(6, min(9, 120 // max(n_cols, 1))))
    ax.set_yticklabels(row_aliases, fontsize=max(6, min(9, 120 // max(n_rows, 1))))
    plt.setp(ax.get_xticklabels(), rotation=90, ha="center", va="top")

    fs = max(6, min(10, 100 // max(n_cols, n_rows, 1)))
    for i in range(n_rows):
        for j in range(n_cols):
            val = grid[i, j]
            if np.isnan(val):
                sym = "—"
            elif val < 0:
                sym = "?"
            elif val >= 1:
                sym = "v"
            else:
                sym = "x"
            ax.text(j, i, sym, ha="center", va="center", fontsize=fs, fontweight="bold", color="#111827")

    ax.set_title(f"Similaridade estrutural JPEG ({title_suffix})", fontsize=9)
    ax.set_xlabel("Questionados" if payload.get("mode") == "with_reference" else "Coluna")
    ax.set_ylabel("Padrão" if payload.get("mode") == "with_reference" else "Linha")

    fig.tight_layout(rect=(0, 0.09, 1, 1))
    _draw_matrix_color_legend(fig)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=96, bbox_inches="tight")
    plt.close(fig)


def render_matrix_txt(payload: dict[str, Any], output_path: Path) -> None:
    """Relatório legível para laudo."""
    matrix = payload.get("matrix") or {}
    mode = payload.get("mode", "all_pairs")
    legend = payload.get("legend") or build_matrix_legend(payload)
    rows = matrix.get("rows") or []
    lines: list[str] = [
        "Comparação de estruturas JPEG — relatório de matriz",
        f"Modo: {mode}",
        f"Critérios (v{payload.get('criteria_version', COMPARISON_CRITERIA_VERSION)}): "
        f"marcadores posicionais, DQT conteúdo, DHT só posição/tipo, thumbnails APP",
        f"Gerado em: {payload.get('generated_at', '—')}",
        "",
        "Legenda alias → arquivo:",
    ]

    for alias in sorted(legend.keys(), key=lambda a: (a[0], int(a[1:]) if a[1:].isdigit() else 0)):
        lines.append(f"  {alias}: {legend[alias]}")

    matches: list[str] = []
    diverges: list[str] = []

    if mode == "with_reference":
        for i, row in enumerate(rows):
            r_alias = _alias_for("reference", i)
            for cell in row.get("cells") or []:
                j = int(cell.get("col_index", 0))
                q_alias = _alias_for("questioned", j)
                pair = f"{r_alias} × {q_alias}"
                if cell.get("unavailable"):
                    diverges.append(f"{pair}: indisponível ({cell.get('reason') or '?'})")
                elif cell.get("matches"):
                    matches.append(pair)
                else:
                    reason = cell.get("reason") or "estrutura divergente"
                    diverges.append(f"{pair}: ✗ ({reason})")
    else:
        for i, row in enumerate(rows):
            q_row = _alias_for("questioned", i)
            for cell in row.get("cells") or []:
                j = int(cell.get("col_index", 0))
                if i == j:
                    continue
                q_col = _alias_for("questioned", j)
                pair = f"{q_row} × {q_col}"
                if cell.get("unavailable"):
                    diverges.append(f"{pair}: indisponível")
                elif cell.get("matches"):
                    matches.append(pair)
                else:
                    reason = cell.get("reason") or "estrutura divergente"
                    diverges.append(f"{pair}: ✗ ({reason})")

    lines.extend(["", f"Coincidências estruturais ({len(matches)}):"])
    if matches:
        for m in matches:
            lines.append(f"  ✓ {m}")
    else:
        lines.append("  (nenhuma)")

    lines.extend(["", f"Divergências ({len(diverges)}):"])
    if diverges:
        for d in diverges[:200]:
            lines.append(f"  {d}")
        if len(diverges) > 200:
            lines.append(f"  … e mais {len(diverges) - 200} pares")
    else:
        lines.append("  (nenhuma)")

    errors = payload.get("errors") or []
    if errors:
        lines.extend(["", "Avisos:"])
        for err in errors:
            lines.append(f"  - {err}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
