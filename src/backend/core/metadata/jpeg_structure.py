"""Leitura de estrutura JPEG via jpegio (quantizacao, Huffman, componentes)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from core.metadata.jpeg_markers import scan_jpeg_marker_sequence

COMPONENT_LABELS = {1: "Y (luminancia)", 2: "Cb", 3: "Cr", 4: "I", 5: "Q"}


def _numpy_to_list(obj: Any) -> Any:
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.integer, np.floating)):
        return obj.item()
    return obj


def _huffman_table_dict(table: dict | None) -> dict[str, Any] | None:
    if not table:
        return None
    counts = table.get("counts")
    symbols = table.get("symbols")
    if counts is None:
        return None
    counts_list = [int(x) for x in np.asarray(counts).flatten()[:16]]
    sym_list = []
    if symbols is not None:
        sym_arr = np.asarray(symbols).flatten()
        total = sum(counts_list)
        sym_list = [int(x) for x in sym_arr[: max(total, 0)]]
    return {
        "counts": counts_list,
        "symbols": sym_list,
        "total_codes": sum(counts_list),
    }


def read_jpeg_structure(path: str) -> dict[str, Any]:
    """Extrai tabelas Q, Huffman e info de componentes de um JPEG."""
    suffix = Path(path).suffix.lower()
    if suffix not in (".jpg", ".jpeg"):
        return {"available": False, "reason": "Arquivo nao e JPEG"}

    try:
        import jpegio as jio
    except ImportError:
        return {"available": False, "reason": "jpegio nao instalado"}

    try:
        struct = jio.read(path)
    except Exception as exc:
        return {"available": False, "reason": f"Falha ao ler JPEG: {exc}"}

    quant_tables: list[dict[str, Any]] = []
    if struct.quant_tables:
        for idx, qt in enumerate(struct.quant_tables):
            matrix = np.asarray(qt, dtype=np.int32)
            label = "luminancia (Y)" if idx == 0 else f"crominancia / tabela {idx}"
            if len(struct.quant_tables) == 2 and idx == 1:
                label = "crominancia (Cb/Cr)"
            quant_tables.append(
                {
                    "index": idx,
                    "label": label,
                    "matrix": matrix.tolist(),
                    "source": "jpegio_bitstream",
                }
            )

    dc_huff: list[dict[str, Any]] = []
    ac_huff: list[dict[str, Any]] = []
    if struct.dc_huff_tables:
        for idx, tbl in enumerate(struct.dc_huff_tables):
            parsed = _huffman_table_dict(tbl)
            if parsed:
                dc_huff.append({"index": idx, "class": "DC", **parsed})
    if struct.ac_huff_tables:
        for idx, tbl in enumerate(struct.ac_huff_tables):
            parsed = _huffman_table_dict(tbl)
            if parsed:
                ac_huff.append({"index": idx, "class": "AC", **parsed})

    components: list[dict[str, Any]] = []
    if struct.comp_info:
        for comp in struct.comp_info:
            cid = int(getattr(comp, "component_id", 0))
            components.append(
                {
                    "component_id": cid,
                    "label": COMPONENT_LABELS.get(cid, f"componente {cid}"),
                    "h_samp_factor": int(getattr(comp, "h_samp_factor", 0)),
                    "v_samp_factor": int(getattr(comp, "v_samp_factor", 0)),
                    "quant_table_index": int(getattr(comp, "quant_tbl_no", -1)),
                    "dc_huff_table_index": int(getattr(comp, "dc_tbl_no", -1)),
                    "ac_huff_table_index": int(getattr(comp, "ac_tbl_no", -1)),
                }
            )

    marker_scan = scan_jpeg_marker_sequence(path)

    return {
        "available": True,
        "progressive": bool(getattr(struct, "progressive_mode", False)),
        "image_width": int(getattr(struct, "image_width", 0)),
        "image_height": int(getattr(struct, "image_height", 0)),
        "num_components": int(getattr(struct, "num_components", 0)),
        "jpeg_color_space": str(getattr(struct, "jpeg_color_space", "")),
        "image_color_space": str(getattr(struct, "image_color_space", "")),
        "quantization_tables": quant_tables,
        "huffman_dc_tables": dc_huff,
        "huffman_ac_tables": ac_huff,
        "components": components,
        "marker_sequence": marker_scan.get("markers", []),
        "marker_count": marker_scan.get("marker_count", 0),
        "marker_summary": marker_scan.get("summary", ""),
        "marker_scan_available": marker_scan.get("available", False),
    }
