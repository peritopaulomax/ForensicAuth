"""Deteccao de dupla compressao JPEG (Popescu & Farid 2004).

Coeficientes DCT quantizados via jpegio; graficos Plotly interativos.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from app.config import get_settings
from core.forensic_plugin import ForensicPlugin
from core.job_staging import job_artifact_dir
from core.progress import pop_progress_callback, report_progress

DCT_ORDER = np.array(
    [
        [1, 2, 6, 7, 15, 16, 28, 29],
        [3, 5, 8, 14, 17, 27, 30, 43],
        [4, 9, 13, 18, 26, 31, 42, 44],
        [10, 12, 19, 25, 32, 41, 45, 54],
        [11, 20, 24, 33, 40, 46, 53, 55],
        [21, 23, 34, 39, 47, 52, 56, 61],
        [22, 35, 38, 48, 51, 57, 60, 62],
        [36, 37, 49, 50, 58, 59, 63, 64],
    ]
)

# Escala fixa do espectro FFT (eixo 0–1000 x 0–600)
FFT_X_MAX = 1000
FFT_Y_MAX = 600


class DoubleCompressionPlugin(ForensicPlugin):
    """DCT coefficient histogram + FFT spectrum per coefficient (interactive)."""

    @property
    def name(self) -> str:
        return "double_compression"

    @property
    def supported_types(self) -> list[str]:
        return ["imagem"]

    def validate_parameters(self, parameters: Dict[str, Any]) -> Tuple[bool, str]:
        dctmin = int(parameters.get("dctmin", 1))
        dctmax = int(parameters.get("dctmax", 5))
        if not (1 <= dctmin <= 64 and 1 <= dctmax <= 64 and dctmin <= dctmax):
            return False, "dctmin e dctmax devem estar entre 1 e 64, com dctmin <= dctmax"
        return True, ""

    def _analyze_coefficient(
        self, coef_lum: np.ndarray, qt_lum: np.ndarray, coeff_index: int
    ) -> Dict[str, Any]:
        ni, nj = np.where(DCT_ORDER == coeff_index)
        ni, nj = int(ni[0]), int(nj[0])
        qt = float(qt_lum[ni, nj])
        dct_i = coef_lum[ni::8, nj::8] * qt

        hist_range = np.arange(-500 * qt, 500 * qt + qt, qt)
        hist, _ = np.histogram(dct_i, bins=hist_range)
        l_hist = np.log(hist + 1e-10)
        df2 = np.diff(l_hist, n=2)
        spectrum = np.abs(np.fft.fft(df2)) ** 2
        norm_spectrum = spectrum / (np.median(spectrum) + 1e-10)

        return {
            "coefficient_index": coeff_index,
            "quant_step": qt,
            "hist_bins": hist_range[:-1].tolist(),
            "hist_values": hist.tolist(),
            "spectrum": norm_spectrum[:FFT_X_MAX].tolist(),
        }

    def _spectrum_layout_patch(self) -> Dict[str, Any]:
        """Eixos do espectro FFT sempre fixos; sem zoom/pan nesse painel."""
        return {
            "xaxis2": {
                "range": [0, FFT_X_MAX],
                "fixedrange": True,
                "title": {"text": "Índice d-fft"},
            },
            "yaxis2": {
                "range": [0, FFT_Y_MAX],
                "fixedrange": True,
                "title": {"text": "|FFT|² / mediana"},
            },
        }

    def _build_interactive_html(self, coefficients: List[Dict[str, Any]], path: Path) -> None:
        """Plotly HTML: histograma interativo + espectro FFT com escala travada."""
        if not coefficients:
            return

        first = coefficients[0]

        fig = make_subplots(
            rows=1,
            cols=2,
            subplot_titles=("Histograma DCT ajustado", "Espectro FFT normalizado"),
            horizontal_spacing=0.08,
        )

        x_spec = list(range(min(FFT_X_MAX, len(first["spectrum"]))))

        fig.add_trace(
            go.Bar(
                x=first["hist_bins"],
                y=first["hist_values"],
                marker_color="#2563eb",
            ),
            row=1,
            col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=x_spec,
                y=first["spectrum"][: len(x_spec)],
                line=dict(color="#dc2626"),
                mode="lines",
            ),
            row=1,
            col=2,
        )

        spec_patch = self._spectrum_layout_patch()

        def _title(cidx: int, qt: float) -> str:
            return f"Coeficiente DCT: {cidx} · q={qt:.0f}"

        fig.update_layout(
            title=_title(first["coefficient_index"], first["quant_step"]),
            height=540,
            showlegend=False,
            uirevision="double_compression_fixed_fft",
            **spec_patch,
        )

        # Histograma: zoom/pan permitido
        fig.update_xaxes(title_text="Valor quantizado", row=1, col=1)
        fig.update_yaxes(title_text="Contagem", row=1, col=1)

        div_id = "double-compression-plot"
        fig.write_html(
            str(path),
            include_plotlyjs="cdn",
            div_id=div_id,
            config={
                "scrollZoom": True,
                "displayModeBar": True,
                "responsive": True,
            },
        )

        self._inject_step_navigation(path, div_id, coefficients)

    def _inject_step_navigation(
        self, path: Path, div_id: str, coefficients: List[Dict[str, Any]]
    ) -> None:
        """Navegacao por coeficiente sem animacao em sequencia (salto direto)."""
        payload = []
        for coeff in coefficients:
            spec = coeff["spectrum"][:FFT_X_MAX]
            payload.append(
                {
                    "idx": coeff["coefficient_index"],
                    "q": coeff["quant_step"],
                    "hb": coeff["hist_bins"],
                    "hv": coeff["hist_values"],
                    "sp": spec,
                }
            )
        coeffs_json = json.dumps(payload)
        last_idx = max(0, len(payload) - 1)
        nav_html = f"""
<div id="dct-nav" style="text-align:center;margin:8px 0 12px;font-family:system-ui,sans-serif;">
  <div style="margin-bottom:0.5rem;font-weight:600;" id="dct-label"></div>
  <div style="display:flex;align-items:center;justify-content:center;gap:0.75rem;flex-wrap:wrap;">
    <button type="button" id="dct-prev" style="padding:6px 14px;cursor:pointer;">◀ Anterior</button>
    <input type="range" id="dct-range" min="0" max="{last_idx}" value="0" step="1"
      style="width:min(520px,70vw);vertical-align:middle;" aria-label="Coeficiente DCT" />
    <button type="button" id="dct-next" style="padding:6px 14px;cursor:pointer;">Próximo ▶</button>
  </div>
</div>
<script>
(function() {{
  var coeffs = {coeffs_json};
  var currentIdx = 0;
  var plotId = {json.dumps(div_id)};
  var rangeEl = document.getElementById('dct-range');
  var labelEl = document.getElementById('dct-label');

  function titleFor(c) {{
    return 'Coeficiente DCT: ' + c.idx + ' · q=' + Math.round(c.q);
  }}

  function updateLabel() {{
    var c = coeffs[currentIdx];
    if (!c) return;
    labelEl.textContent = titleFor(c);
    if (rangeEl) rangeEl.value = String(currentIdx);
  }}

  function showAt(idx) {{
    currentIdx = Math.max(0, Math.min(coeffs.length - 1, idx));
    var gd = document.getElementById(plotId);
    var c = coeffs[currentIdx];
    if (!gd || !c || !window.Plotly) return;
    var n = c.sp.length;
    var specX = Array.from({{ length: n }}, function(_, j) {{ return j; }});
    Plotly.restyle(plotId, {{ x: [c.hb, specX], y: [c.hv, c.sp] }}, [0, 1]);
    Plotly.relayout(plotId, {{ 'title.text': titleFor(c) }});
    updateLabel();
  }}

  document.getElementById('dct-prev').onclick = function() {{ showAt(currentIdx - 1); }};
  document.getElementById('dct-next').onclick = function() {{ showAt(currentIdx + 1); }};
  if (rangeEl) {{
    rangeEl.oninput = function() {{ showAt(parseInt(rangeEl.value, 10) || 0); }};
  }}

  function waitPlot() {{
    var gd = document.getElementById(plotId);
    if (!gd || !gd.data || !window.Plotly) {{
      setTimeout(waitPlot, 80);
      return;
    }}
    updateLabel();
  }}
  waitPlot();
}})();
</script>
"""
        html = path.read_text(encoding="utf-8")
        if '<div id="dct-nav"' not in html:
            html = html.replace("<body>", f"<body>{nav_html}", 1)
        path.write_text(html, encoding="utf-8")

    def analyze(self, evidence_path: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        on_progress = pop_progress_callback(parameters)
        try:
            try:
                import jpegio as jio
            except ImportError:
                return {
                    "success": False,
                    "error": "jpegio nao instalado — necessario para dupla compressao",
                    "adapter": "double_compression",
                }

            if not evidence_path.lower().endswith((".jpg", ".jpeg")):
                return {
                    "success": False,
                    "error": "Evidencia deve ser arquivo JPEG",
                    "adapter": "double_compression",
                }

            report_progress(on_progress, 10, "Lendo coeficientes JPEG (jpegio)")
            jpeg = jio.read(evidence_path)
            coef_lum = jpeg.coef_arrays[0]
            qt_lum = jpeg.quant_tables[0]

            dctmin = int(parameters.get("dctmin", 1))
            dctmax = int(parameters.get("dctmax", 5))
            total = max(1, dctmax - dctmin + 1)

            coefficients = []
            for idx, coeff in enumerate(range(dctmin, dctmax + 1)):
                pct = 15 + int((idx / total) * 65)
                report_progress(on_progress, pct, f"Coeficiente DCT {coeff}/{dctmax}")
                raw = self._analyze_coefficient(coef_lum, qt_lum, coeff)
                coefficients.append(raw)

            report_progress(on_progress, 82, "Montando grafico Plotly")
            settings = get_settings()
            result_dir = job_artifact_dir(parameters, fallback_subdir="double_compression_tmp")
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            html_path = result_dir / f"interactive_{stamp}.html"

            self._build_interactive_html(coefficients, html_path)

            return {
                "success": True,
                "adapter": "double_compression",
                "status": "completed",
                "dctmin": dctmin,
                "dctmax": dctmax,
                "coefficient_count": len(coefficients),
                "coefficient_indices": [c["coefficient_index"] for c in coefficients],
                "fft_axis_x_max": FFT_X_MAX,
                "fft_axis_y_max": FFT_Y_MAX,
                "quantization_table_luma": qt_lum.tolist(),
                "interactive_html_path": str(html_path),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as exc:
            return {"success": False, "error": str(exc), "adapter": "double_compression"}
