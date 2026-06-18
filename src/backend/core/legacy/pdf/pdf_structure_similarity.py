"""Metricas de similaridade entre grafos estruturais PDF — portado de estrutura_pdf_metricas.ipynb."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import seaborn as sns

from core.legacy.pdf.pdf_structure_graph import parse_pdf_structure

ProgressFn = Optional[Callable[[int, str], None]]


def jaccard_similarity(set1: set, set2: set) -> float:
    if not set1 and not set2:
        return 1.0
    intersection = len(set1 & set2)
    union = len(set1 | set2)
    if union == 0:
        return 0.0
    return intersection / union


def weisfeiler_lehman_features(graph: nx.DiGraph, iterations: int = 3) -> Counter:
    if isinstance(graph, nx.DiGraph):
        working_graph = graph.to_undirected()
    else:
        working_graph = graph.copy()

    labels = {node: data.get("label", str(node)) for node, data in working_graph.nodes(data=True)}
    feature_counter: Counter = Counter(labels.values())

    for _ in range(iterations):
        new_labels = {}
        for node in working_graph.nodes():
            neighbors = sorted(labels[neighbor] for neighbor in working_graph.neighbors(node))
            new_label = labels[node] + "|" + "-".join(neighbors)
            new_labels[node] = new_label
        labels = new_labels
        feature_counter.update(labels.values())

    return feature_counter


def build_wl_feature_matrix(
    graphs: Sequence[nx.DiGraph], iterations: int = 3
) -> Tuple[np.ndarray, List[str]]:
    feature_dicts: List[Dict[str, int]] = []
    feature_set: set = set()

    for graph in graphs:
        features = weisfeiler_lehman_features(graph, iterations=iterations)
        feature_dicts.append(dict(features))
        feature_set.update(features.keys())

    feature_list = sorted(feature_set)
    if not feature_list:
        return np.zeros((len(graphs), 0)), feature_list

    matrix = np.zeros((len(graphs), len(feature_list)), dtype=float)
    for i, features in enumerate(feature_dicts):
        for j, feature in enumerate(feature_list):
            matrix[i, j] = features.get(feature, 0)

    return matrix, feature_list


def graph_jaccard_similarity(graph1: nx.DiGraph, graph2: nx.DiGraph) -> float:
    node_labels_1 = {data.get("label", str(node)) for node, data in graph1.nodes(data=True)}
    node_labels_2 = {data.get("label", str(node)) for node, data in graph2.nodes(data=True)}
    node_sim = jaccard_similarity(node_labels_1, node_labels_2)

    edge_labels_1 = {
        (graph1.nodes[u].get("label", str(u)), graph1.nodes[v].get("label", str(v)), data.get("key", ""))
        for u, v, data in graph1.edges(data=True)
    }
    edge_labels_2 = {
        (graph2.nodes[u].get("label", str(u)), graph2.nodes[v].get("label", str(v)), data.get("key", ""))
        for u, v, data in graph2.edges(data=True)
    }
    edge_sim = jaccard_similarity(edge_labels_1, edge_labels_2)
    return (node_sim + edge_sim) / 2


def compute_wl_kernel_square(graphs: Sequence[nx.DiGraph], iterations: int = 3) -> np.ndarray:
    feature_matrix, _ = build_wl_feature_matrix(graphs, iterations=iterations)
    if feature_matrix.size == 0:
        n = len(graphs)
        return np.ones((n, n))

    kernel = feature_matrix @ feature_matrix.T
    diagonal = np.diag(kernel)
    norms = np.sqrt(np.clip(diagonal, a_min=1e-12, a_max=None))
    normalization = np.outer(norms, norms)
    return np.divide(kernel, normalization, out=np.zeros_like(kernel), where=normalization != 0)


def compute_wl_cross_kernel(
    ref_graphs: Sequence[nx.DiGraph],
    quest_graphs: Sequence[nx.DiGraph],
    iterations: int = 3,
) -> np.ndarray:
    """Matriz |questionados| x |referencias| com kernel WL normalizado."""
    if not ref_graphs or not quest_graphs:
        return np.zeros((len(quest_graphs), len(ref_graphs)))

    all_graphs = list(ref_graphs) + list(quest_graphs)
    feature_matrix, _ = build_wl_feature_matrix(all_graphs, iterations=iterations)
    if feature_matrix.size == 0:
        return np.ones((len(quest_graphs), len(ref_graphs)))

    n_ref = len(ref_graphs)
    ref_fm = feature_matrix[:n_ref]
    quest_fm = feature_matrix[n_ref:]
    kernel = quest_fm @ ref_fm.T
    q_norms = np.sqrt(np.clip(np.diag(quest_fm @ quest_fm.T), a_min=1e-12, a_max=None))
    r_norms = np.sqrt(np.clip(np.diag(ref_fm @ ref_fm.T), a_min=1e-12, a_max=None))
    denom = np.outer(q_norms, r_norms)
    return np.divide(kernel, denom, out=np.zeros_like(kernel), where=denom != 0)


def compute_jaccard_square(graphs: Sequence[nx.DiGraph]) -> np.ndarray:
    n = len(graphs)
    matrix = np.zeros((n, n))
    for i in range(n):
        for j in range(i, n):
            score = graph_jaccard_similarity(graphs[i], graphs[j])
            matrix[i, j] = matrix[j, i] = score
    return matrix


def compute_jaccard_cross(
    ref_graphs: Sequence[nx.DiGraph], quest_graphs: Sequence[nx.DiGraph]
) -> np.ndarray:
    matrix = np.zeros((len(quest_graphs), len(ref_graphs)))
    for i, qg in enumerate(quest_graphs):
        for j, rg in enumerate(ref_graphs):
            matrix[i, j] = graph_jaccard_similarity(qg, rg)
    return matrix


def _axis_legend(
    full_labels: Sequence[str],
    prefix: str,
) -> Tuple[List[str], List[Dict[str, str]]]:
    """Gera rotulos curtos para eixos e mapeamento ref -> nome completo."""
    short = [f"{prefix}{idx}" for idx in range(1, len(full_labels) + 1)]
    legend = [{"ref": ref, "filename": name} for ref, name in zip(short, full_labels)]
    return short, legend


def _parse_graphs(
    paths: Sequence[str],
    labels: Sequence[str],
    reporter: ProgressFn,
    phase: str,
) -> List[nx.DiGraph]:
    graphs: List[nx.DiGraph] = []
    total = len(paths)
    for idx, path in enumerate(paths):
        if reporter:
            pct = 5 + int(40 * idx / max(total, 1))
            reporter(pct, f"{phase}: {labels[idx] if idx < len(labels) else path}")
        graphs.append(parse_pdf_structure(path))
    return graphs


def render_similarity_heatmap(
    matrix: np.ndarray,
    row_short: Sequence[str],
    col_short: Sequence[str],
    row_legend: Sequence[Dict[str, str]],
    col_legend: Sequence[Dict[str, str]],
    title: str,
    output_path: Path,
    *,
    cross_mode: bool,
) -> None:
    """Heatmap com eixos compactos (Q1, R1, PDF 1…) e legenda com nomes completos."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    n_row, n_col = matrix.shape
    fig_w = max(7, min(16, 0.55 * n_col + 3))
    heat_h = max(3.5, min(14, 0.45 * n_row + 2.5))
    legend_rows = len(row_legend) + len(col_legend) + (2 if cross_mode else 1)
    legend_h = max(1.2, min(8, 0.22 * legend_rows + 0.6))

    fig = plt.figure(figsize=(fig_w, heat_h + legend_h))
    gs = fig.add_gridspec(2, 1, height_ratios=[heat_h, legend_h], hspace=0.28)
    ax_hm = fig.add_subplot(gs[0])
    ax_leg = fig.add_subplot(gs[1])
    ax_leg.axis("off")

    sns.heatmap(
        matrix,
        annot=n_row <= 12 and n_col <= 12,
        fmt=".3f",
        cmap="PiYG",
        vmin=0,
        vmax=1,
        xticklabels=list(col_short),
        yticklabels=list(row_short),
        ax=ax_hm,
    )
    ax_hm.set_title(title)
    ax_hm.set_xlabel("Referencia" if cross_mode else "PDF")
    ax_hm.set_ylabel("Questionado" if cross_mode else "PDF")
    ax_hm.tick_params(axis="x", rotation=0)
    ax_hm.tick_params(axis="y", rotation=0)

    table_rows: List[List[str]] = []
    if cross_mode:
        table_rows.append(["Questionados", ""])
        table_rows.extend([[entry["ref"], entry["filename"]] for entry in row_legend])
        table_rows.append(["", ""])
        table_rows.append(["Referencias", ""])
        table_rows.extend([[entry["ref"], entry["filename"]] for entry in col_legend])
    else:
        table_rows.append(["Ref.", "Arquivo"])
        table_rows.extend([[entry["ref"], entry["filename"]] for entry in row_legend])

    display_rows = [row for row in table_rows if row != ["", ""]]
    section_headers = {idx for idx, row in enumerate(display_rows) if row[1] == "" and row[0]}

    table = ax_leg.table(
        cellText=display_rows,
        colWidths=[0.12, 0.88],
        loc="upper left",
        cellLoc="left",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(8)
    table.scale(1, 1.15)

    for (row_idx, col_idx), cell in table.get_celld().items():
        if col_idx == 0 and row_idx in section_headers:
            cell.set_text_props(weight="bold")
            cell.set_facecolor("#f3f4f6")

    fig.savefig(output_path, format="PNG", bbox_inches="tight", dpi=120)
    plt.close(fig)


def run_similarity_analysis(
    *,
    mode: str,
    reference_paths: Sequence[str],
    reference_labels: Sequence[str],
    questioned_paths: Sequence[str],
    questioned_labels: Sequence[str],
    out_dir: Path,
    metrics: Optional[Sequence[str]] = None,
    reporter: ProgressFn = None,
) -> Dict[str, Any]:
    """mode: with_reference | all_pairs."""
    chosen = list(metrics or ("jaccard", "wl_kernel"))
    out_dir.mkdir(parents=True, exist_ok=True)

    if mode == "with_reference":
        if not reference_paths:
            raise ValueError("Informe ao menos um PDF de referencia")
        if not questioned_paths:
            raise ValueError("Informe ao menos um PDF questionado")
        ref_graphs = _parse_graphs(reference_paths, reference_labels, reporter, "Referencias")
        quest_graphs = _parse_graphs(questioned_paths, questioned_labels, reporter, "Questionados")
        row_full = list(questioned_labels)
        col_full = list(reference_labels)
        row_short, row_legend = _axis_legend(row_full, "Q")
        col_short, col_legend = _axis_legend(col_full, "R")
        cross_mode = True
    elif mode == "all_pairs":
        if len(questioned_paths) < 2:
            raise ValueError("Modo sem referencia exige ao menos 2 PDFs questionados")
        all_paths = list(questioned_paths)
        all_labels = list(questioned_labels)
        ref_graphs = []
        graphs = _parse_graphs(all_paths, all_labels, reporter, "PDFs")
        quest_graphs = graphs
        row_full = col_full = all_labels
        row_short, row_legend = _axis_legend(row_full, "PDF ")
        col_short, col_legend = row_short, row_legend
        cross_mode = False
    else:
        raise ValueError(f"Modo invalido: {mode}")

    results: Dict[str, Any] = {
        "mode": mode,
        "reference_count": len(reference_paths),
        "questioned_count": len(questioned_paths),
        "metrics": {},
    }

    if reporter:
        reporter(55, "Calculando similaridade Jaccard")

    if "jaccard" in chosen:
        if mode == "with_reference":
            j_mat = compute_jaccard_cross(ref_graphs, quest_graphs)
        else:
            j_mat = compute_jaccard_square(quest_graphs)
        j_path = out_dir / "similarity_jaccard.png"
        render_similarity_heatmap(
            j_mat,
            row_short,
            col_short,
            row_legend,
            col_legend,
            "Similaridade estrutural (Jaccard)",
            j_path,
            cross_mode=cross_mode,
        )
        results["metrics"]["jaccard"] = {
            "matrix": j_mat.tolist(),
            "row_labels": row_full,
            "col_labels": col_full,
            "row_short_labels": row_short,
            "col_short_labels": col_short,
            "row_legend": row_legend,
            "col_legend": col_legend,
            "heatmap_path": str(j_path),
        }

    if reporter:
        reporter(72, "Calculando kernel Weisfeiler-Lehman")

    if "wl_kernel" in chosen:
        if mode == "with_reference":
            wl_mat = compute_wl_cross_kernel(ref_graphs, quest_graphs)
        else:
            wl_mat = compute_wl_kernel_square(quest_graphs)
        wl_path = out_dir / "similarity_wl_kernel.png"
        render_similarity_heatmap(
            wl_mat,
            row_short,
            col_short,
            row_legend,
            col_legend,
            "Similaridade estrutural (WL kernel)",
            wl_path,
            cross_mode=cross_mode,
        )
        results["metrics"]["wl_kernel"] = {
            "matrix": wl_mat.tolist(),
            "row_labels": row_full,
            "col_labels": col_full,
            "row_short_labels": row_short,
            "col_short_labels": col_short,
            "row_legend": row_legend,
            "col_legend": col_legend,
            "heatmap_path": str(wl_path),
        }

    json_path = out_dir / "similarity_matrices.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    if reporter:
        reporter(85, "Matrizes salvas")

    out: Dict[str, Any] = {
        "similarity_json_path": str(json_path),
        "mode": mode,
    }
    if "jaccard" in results["metrics"]:
        out["similarity_jaccard_image_path"] = results["metrics"]["jaccard"]["heatmap_path"]
    if "wl_kernel" in results["metrics"]:
        out["similarity_wl_kernel_image_path"] = results["metrics"]["wl_kernel"]["heatmap_path"]
    return out
