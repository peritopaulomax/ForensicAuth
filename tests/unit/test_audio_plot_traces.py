"""Serializacao de figuras Plotly para comparacao no cliente."""

import base64
import struct

import numpy as np
import plotly.graph_objects as go

from core.legacy.audio.audio_plotly_util import (
    decode_plotly_binary_array,
    serialize_figure_for_overlay,
    write_plot_traces_json,
)


def test_serialize_figure_for_overlay_line_trace(tmp_path):
    fig = go.Figure(
        data=[go.Scatter(x=[0, 1, 2], y=[1.0, 2.0, 1.5], mode="lines", name="test")],
        layout={"title": "Titulo", "xaxis": {"title": "Tempo"}, "yaxis": {"title": "Hz"}},
    )
    payload = serialize_figure_for_overlay(fig)
    assert len(payload["traces"]) == 1
    assert payload["traces"][0]["x"] == [0, 1, 2]
    assert payload["traces"][0]["y"] == [1.0, 2.0, 1.5]
    assert payload["layout_title"] == "Titulo"
    assert payload["xaxis_title"] == "Tempo"

    out = tmp_path / "plot_traces.json"
    write_plot_traces_json(fig, out)
    assert out.exists()


def test_serialize_large_arrays_as_lists_not_bdata():
    n = 5000
    x = np.linspace(0, 10, n)
    y = np.sin(x)
    fig = go.Figure(data=[go.Scatter(x=x, y=y, mode="lines")])
    payload = serialize_figure_for_overlay(fig)
    trace = payload["traces"][0]
    assert isinstance(trace["x"], list)
    assert isinstance(trace["y"], list)
    assert len(trace["x"]) == n


def test_decode_plotly_binary_array_roundtrip():
    values = [1.5, -2.25, 0.0, 100.5]
    arr = np.array(values, dtype=np.float64)
    encoded = {
        "dtype": "f8",
        "bdata": base64.b64encode(arr.tobytes()).decode("ascii"),
    }
    decoded = decode_plotly_binary_array(encoded)
    assert len(decoded) == len(values)
    for a, b in zip(decoded, values):
        assert abs(a - b) < 1e-9
