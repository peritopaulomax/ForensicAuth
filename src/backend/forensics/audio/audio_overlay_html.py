"""HTML Plotly da comparacao de audio, montado a partir dos JSON de cada job."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import plotly.graph_objects as go

from forensics.audio.audio_plotly_util import decode_plotly_binary_array, write_plot_html

# Nome do derivado -> painel LTAS. None = plot_traces.json (ENF, niveis, DC).
AUDIO_OVERLAY_HTML_FILES: dict[str, str | None] = {
    "enf_overlay.html": None,
    "levels_overlay.html": None,
    "dc_overlay.html": None,
    "ltas_normal_overlay.html": "normal",
    "ltas_6db_overlay.html": "6db",
    "ltas_sorted_overlay.html": "sorted",
    "ltas_derivative_overlay.html": "derivative",
}

_PANEL_TITLES = {
    "normal": "LTAS normal",
    "6db": "LTAS 6 dB/oitava",
    "sorted": "LTAS ordenado",
    "derivative": "Derivada LTAS ordenado",
}

_COLOR_PAIRS = (
    ("#2563eb", "#dc2626"),
    ("#16a34a", "#ea580c"),
    ("#9333ea", "#92400e"),
    ("#db2777", "#6b7280"),
    ("#0891b2", "#c026d3"),
    ("#65a30d", "#1e3a8a"),
)


def _as_floats(values: Any) -> list[float]:
    if values is None:
        return []
    if isinstance(values, dict) and "bdata" in values:
        return decode_plotly_binary_array(values)
    if isinstance(values, list):
        return [float(v) for v in values]
    return []


def _short_trace_label(raw: str) -> str:
    name = (raw or "").strip()
    if not name:
        return "série"
    lowered = name.lower()
    if "esquerdo" in lowered:
        return "Canal esquerdo"
    if "direito" in lowered:
        return "Canal direito"
    if "único" in lowered or "unico" in lowered:
        return "Canal único"
    if "ltas" in lowered:
        return name[-24:]
    if "desvio" in lowered:
        return "ENF"
    return name if len(name) <= 28 else f"{name[:28]}…"


def load_plot_bundle(result_dir: Path, panel: str | None) -> dict[str, Any]:
    if panel:
        path = result_dir / "ltas_plot_data.json"
        if not path.is_file():
            raise FileNotFoundError("ltas_plot_data.json nao encontrado")
        data = json.loads(path.read_text(encoding="utf-8"))
        bundle = data.get(panel) if isinstance(data, dict) else None
        if not isinstance(bundle, dict):
            raise FileNotFoundError(f"Painel LTAS '{panel}' ausente")
        return bundle
    path = result_dir / "plot_traces.json"
    if not path.is_file():
        raise FileNotFoundError("plot_traces.json nao encontrado")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise FileNotFoundError("plot_traces.json invalido")
    return data


def compose_overlay_figure(
    layers: list[tuple[str, dict[str, Any]]],
    *,
    panel_title: str | None = None,
) -> go.Figure:
    """Monta a figura com a mesma paleta da tela de comparacao."""
    compare = len(layers) > 1
    fig = go.Figure()
    xaxis_title = ""
    yaxis_title = ""
    for audio_index, (evidence_label, bundle) in enumerate(layers):
        traces = bundle.get("traces") if isinstance(bundle, dict) else None
        if not isinstance(traces, list) or not traces:
            raise ValueError(f"Job sem tracos para '{evidence_label}'")
        if not xaxis_title:
            xaxis_title = str(bundle.get("xaxis_title") or "")
        if not yaxis_title:
            yaxis_title = str(bundle.get("yaxis_title") or "")
        c0, c1 = _COLOR_PAIRS[audio_index % len(_COLOR_PAIRS)]
        for trace_index, trace in enumerate(traces):
            if not isinstance(trace, dict):
                continue
            base_name = str(trace.get("name") or "série").strip() or "série"
            width = 2
            line = trace.get("line") if isinstance(trace.get("line"), dict) else {}
            if line.get("width") is not None:
                width = line.get("width")
            if not compare:
                color = line.get("color") or c0
                legend = base_name
                hover = trace.get("hovertemplate") or f"{base_name}<br>%{{x}}<br>%{{y}}<extra></extra>"
            else:
                color = c0 if len(traces) == 1 or trace_index % 2 == 0 else c1
                short = _short_trace_label(base_name)
                legend = (
                    f"Áudio {audio_index + 1} — {short}"
                    if len(traces) > 1
                    else f"Áudio {audio_index + 1}"
                )
                hover = f"{legend} — {evidence_label}<br>%{{x}}<br>%{{y}}<extra></extra>"
            fig.add_trace(
                go.Scatter(
                    x=_as_floats(trace.get("x")),
                    y=_as_floats(trace.get("y")),
                    mode=str(trace.get("mode") or "lines"),
                    name=legend,
                    line={"color": color, "width": width},
                    hovertemplate=hover,
                )
            )

    title = panel_title or ""
    fig.update_layout(
        title={"text": title, "x": 0.02, "xanchor": "left"} if title else None,
        autosize=True,
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        hovermode="x unified",
        showlegend=compare or len(fig.data) > 1,
        margin={"l": 64, "r": 140 if compare else 72, "t": 72 if title else 48, "b": 52},
        legend={
            "orientation": "v",
            "yanchor": "top",
            "xanchor": "left",
            "x": 1.02,
            "y": 1,
        },
        xaxis={"title": {"text": xaxis_title}, "showgrid": True, "zeroline": True},
        yaxis={"title": {"text": yaxis_title}, "showgrid": True, "zeroline": True},
    )
    return fig


def write_overlay_html(
    result_dir: Path,
    filename: str,
    layers: list[tuple[str, dict[str, Any]]],
) -> Path:
    if filename not in AUDIO_OVERLAY_HTML_FILES:
        raise ValueError(f"HTML de comparacao desconhecido: {filename}")
    panel = AUDIO_OVERLAY_HTML_FILES[filename]
    fig = compose_overlay_figure(layers, panel_title=_PANEL_TITLES.get(panel or ""))
    dest = result_dir / filename
    write_plot_html(fig, dest, div_id="audio-overlay")
    return dest
