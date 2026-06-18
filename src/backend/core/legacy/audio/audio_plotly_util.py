"""Serializacao de figuras Plotly para comparacao no cliente."""

from __future__ import annotations

import base64
import json
import struct
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import plotly.graph_objects as go

from core.legacy.audio.forensics_analyzer import AudioForensicsAnalyzer

_analyzer: AudioForensicsAnalyzer | None = None

_DTYPE_MAP = {
    "i1": "b",
    "u1": "B",
    "i2": "h",
    "u2": "H",
    "i4": "i",
    "u4": "I",
    "f4": "f",
    "f8": "d",
}


def get_analyzer() -> AudioForensicsAnalyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = AudioForensicsAnalyzer()
    return _analyzer


def _tolist(values: Any) -> List[float]:
    if values is None:
        return []
    if isinstance(values, dict) and "bdata" in values:
        return decode_plotly_binary_array(values)
    if isinstance(values, np.ndarray):
        return values.astype(float).tolist()
    if hasattr(values, "tolist"):
        return list(values.tolist())
    return [float(v) for v in values]


def decode_plotly_binary_array(obj: dict) -> List[float]:
    """Decodifica {dtype, bdata} do JSON Plotly para lista JS-compativel."""
    dtype = str(obj.get("dtype", "f8"))
    fmt = _DTYPE_MAP.get(dtype, "d")
    raw = base64.b64decode(obj["bdata"])
    count = len(raw) // struct.calcsize(fmt)
    return [float(v) for v in struct.unpack(f"<{count}{fmt}", raw)]


def _axis_title(layout: Any, axis_key: str) -> str:
    axis = getattr(layout, axis_key, None) if layout is not None else None
    if axis is None and isinstance(layout, dict):
        axis = layout.get(axis_key) or {}
    title = getattr(axis, "title", None) if axis is not None else None
    if isinstance(axis, dict):
        title = axis.get("title")
    if title is None:
        return ""
    if isinstance(title, dict):
        return str(title.get("text", ""))
    text = getattr(title, "text", None)
    if text is not None:
        return str(text)
    return str(title)


def _trace_to_json(tr: Any) -> Dict[str, Any]:
    trace: Dict[str, Any] = {
        "type": getattr(tr, "type", "scatter") or "scatter",
        "name": getattr(tr, "name", "") or "",
    }
    if getattr(tr, "x", None) is not None:
        trace["x"] = _tolist(tr.x)
    if getattr(tr, "y", None) is not None:
        trace["y"] = _tolist(tr.y)
    mode = getattr(tr, "mode", None)
    if mode:
        trace["mode"] = mode
    hover = getattr(tr, "hovertemplate", None)
    if hover:
        trace["hovertemplate"] = hover
    line = getattr(tr, "line", None)
    if line is not None:
        color = getattr(line, "color", None)
        width = getattr(line, "width", None)
        if color or width:
            trace["line"] = {
                "color": color,
                "width": width if width is not None else 1.5,
            }
    return trace


def serialize_figure_for_overlay(fig: go.Figure) -> Dict[str, Any]:
    """Extrai tracos com arrays numericos (nao bdata) para Plotly.js no browser."""
    traces = [_trace_to_json(tr) for tr in fig.data]
    layout = fig.layout
    title = layout.title.text if layout.title and layout.title.text else ""
    width = getattr(layout, "width", None)
    height = getattr(layout, "height", None)
    return {
        "traces": traces,
        "layout_title": title,
        "xaxis_title": _axis_title(layout, "xaxis"),
        "yaxis_title": _axis_title(layout, "yaxis"),
        "layout_width": int(width) if width is not None else None,
        "layout_height": int(height) if height is not None else None,
    }


def write_plot_traces_json(fig: go.Figure, path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = serialize_figure_for_overlay(fig)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


def write_ltas_plot_data_json(figures: List[go.Figure], path: Path) -> str:
    keys = ("normal", "6db", "sorted", "derivative")
    payload = {
        key: serialize_figure_for_overlay(fig)
        for key, fig in zip(keys, figures)
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


_RESPONSIVE_HTML_HEAD = """
<style>
  html, body {
    margin: 0;
    padding: 0;
    width: 100%;
    height: 100%;
    overflow: hidden;
    background: #fff;
  }
  .plotly-graph-div, .js-plotly-plot {
    width: 100% !important;
    max-width: 100% !important;
    height: 100% !important;
  }
</style>
<script>
  function vaResizePlotly() {
    var gd = document.querySelector(".plotly-graph-div");
    if (gd && window.Plotly) window.Plotly.Plots.resize(gd);
  }
  window.addEventListener("resize", vaResizePlotly);
  window.addEventListener("load", function () {
    vaResizePlotly();
    setTimeout(vaResizePlotly, 80);
    setTimeout(vaResizePlotly, 400);
  });
</script>
"""


def _prepare_responsive_figure(fig: go.Figure) -> go.Figure:
    """Remove dimensões fixas para o Plotly preencher o iframe/container."""
    fig.update_layout(autosize=True)
    fig.update_layout(width=None, height=None)
    return fig


def write_plot_html(fig: go.Figure, path: Path, *, div_id: str = "audio-plot") -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    _prepare_responsive_figure(fig)
    fig.write_html(
        str(path),
        include_plotlyjs="cdn",
        full_html=True,
        config={"responsive": True, "displayModeBar": True, "displaylogo": False},
        div_id=div_id,
    )
    html = path.read_text(encoding="utf-8")
    if "</head>" in html and "vaResizePlotly" not in html:
        html = html.replace("</head>", f"{_RESPONSIVE_HTML_HEAD}</head>", 1)
        path.write_text(html, encoding="utf-8")
    return str(path)


def write_plots(
    figures: List[Tuple[str, go.Figure]],
    result_dir: Path,
) -> Dict[str, str]:
    """Salva varias figuras; retorna chaves *_html_path para o job."""
    out: Dict[str, str] = {}
    for key, fig in figures:
        p = result_dir / f"{key}.html"
        write_plot_html(fig, p, div_id=f"audio-{key}")
        out[f"{key}_html_path"] = str(p)
    ltas_path = result_dir / "ltas_plot_data.json"
    write_ltas_plot_data_json(
        [fig for _, fig in figures],
        ltas_path,
    )
    out["ltas_plot_data_json_path"] = str(ltas_path)
    return out
