/** Tema Plotly padrao para visualizacoes forenses de audio. */

export const PLOTLY_FORENSIC_CONFIG = {
  responsive: true,
  displayModeBar: true,
  displaylogo: false,
  scrollZoom: true,
  modeBarButtonsToRemove: ["lasso2d", "select2d", "autoScale2d"],
};

export function forensicAxis(title: string) {
  return {
    title: { text: title, font: { size: 12, color: "#374151" } },
    showgrid: true,
    gridcolor: "#d1d5db",
    zeroline: true,
    zerolinecolor: "#9ca3af",
    linewidth: 1,
  };
}

export function buildForensicLayout(options: {
  panelTitle?: string;
  xaxisTitle?: string;
  yaxisTitle?: string;
  width?: number;
  height?: number;
  traceCount: number;
  compareCount: number;
  showLegend?: boolean;
}): Record<string, unknown> {
  const {
    panelTitle,
    xaxisTitle = "",
    yaxisTitle = "",
    width,
    height = 500,
    traceCount,
    compareCount,
    showLegend = compareCount > 1,
  } = options;

  const multiCompare = compareCount > 1;
  const topMargin = panelTitle ? (multiCompare ? 72 : 56) : multiCompare ? 64 : 48;
  const rightMargin = showLegend ? (multiCompare ? 120 : 72) : 32;

  const layout: Record<string, unknown> = {
    autosize: width == null,
    width: width ?? undefined,
    height,
    paper_bgcolor: "#ffffff",
    plot_bgcolor: "#ffffff",
    font: { family: "Segoe UI, system-ui, sans-serif", size: 12, color: "#1f2937" },
    margin: { l: 64, r: rightMargin, t: topMargin, b: 52 },
    hovermode: "x unified",
    showlegend: showLegend,
    xaxis: forensicAxis(xaxisTitle),
    yaxis: forensicAxis(yaxisTitle),
  };

  if (panelTitle) {
    layout.title = {
      text: panelTitle,
      font: { size: 14, color: "#111827" },
      x: 0.02,
      xanchor: "left",
    };
  }

  if (showLegend) {
    layout.legend = multiCompare
      ? {
          orientation: "v",
          yanchor: "top",
          xanchor: "left",
          x: 1.02,
          y: 1,
          bgcolor: "rgba(255,255,255,0.92)",
          bordercolor: "#e5e7eb",
          borderwidth: 1,
          font: { size: 11 },
        }
      : {
          orientation: "h",
          yanchor: "bottom",
          y: 1.02,
          xanchor: "right",
          x: 1,
          font: { size: 11 },
        };
  }

  if (traceCount > 0 && !multiCompare) {
    layout.showlegend = traceCount > 1;
  }

  return layout;
}
