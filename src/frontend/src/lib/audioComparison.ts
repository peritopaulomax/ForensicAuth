/** Paleta de cores para comparacao de multiplos audios nos graficos Plotly. */
export const AUDIO_OVERLAY_COLOR_PAIRS: ReadonlyArray<readonly [string, string]> = [
  ["#2563eb", "#dc2626"],
  ["#16a34a", "#ea580c"],
  ["#9333ea", "#92400e"],
  ["#db2777", "#6b7280"],
  ["#0891b2", "#c026d3"],
  ["#65a30d", "#1e3a8a"],
];

export interface PlotTraceJson {
  type?: string;
  x?: number[] | unknown;
  y?: number[] | unknown;
  name?: string;
  mode?: string;
  hovertemplate?: string;
  line?: { color?: string; width?: number };
}

function decodePlotlyBinaryArray(obj: { dtype?: string; bdata: string }): number[] {
  const dtype = obj.dtype || "f8";
  const raw = atob(obj.bdata);
  const bytes = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);

  if (dtype === "f8") {
    return Array.from(new Float64Array(bytes.buffer));
  }
  if (dtype === "f4") {
    return Array.from(new Float32Array(bytes.buffer));
  }
  return [];
}

export function normalizePlotArray(val: unknown): number[] {
  if (val == null) return [];
  if (Array.isArray(val)) return val.map(Number);
  if (typeof val === "object" && val !== null && "bdata" in val) {
    return decodePlotlyBinaryArray(val as { dtype?: string; bdata: string });
  }
  return [];
}

export interface PlotBundleJson {
  traces: PlotTraceJson[];
  layout_title?: string;
  xaxis_title?: string;
  yaxis_title?: string;
  layout_width?: number;
  layout_height?: number;
}

export interface AudioOverlayLayer {
  evidenceLabel: string;
  bundle: PlotBundleJson;
}

export type LtasPanelKey = "normal" | "6db" | "sorted" | "derivative";

export const LTAS_PANELS: { key: LtasPanelKey; title: string }[] = [
  { key: "normal", title: "LTAS normal" },
  { key: "6db", title: "LTAS 6 dB/oitava" },
  { key: "sorted", title: "LTAS ordenado" },
  { key: "derivative", title: "Derivada LTAS ordenado" },
];

export function colorPairForAudioIndex(index: number): readonly [string, string] {
  return AUDIO_OVERLAY_COLOR_PAIRS[index % AUDIO_OVERLAY_COLOR_PAIRS.length];
}

function shortTraceLabel(raw: string): string {
  const n = raw.trim();
  if (!n) return "série";
  if (n.includes("esquerdo") || n.includes("Esquerdo")) return "Canal esquerdo";
  if (n.includes("direito") || n.includes("Direito")) return "Canal direito";
  if (n.includes("Único") || n.includes("único")) return "Canal único";
  if (n.includes("LTAS")) return n.replace(/^.*LTAS/i, "LTAS").slice(0, 24);
  if (n.includes("Desvio")) return "ENF";
  return n.length > 28 ? `${n.slice(0, 28)}…` : n;
}

export function tracesForOverlayLayer(
  layer: AudioOverlayLayer,
  audioIndex: number,
  compareMode: boolean
): PlotTraceJson[] {
  const [c0, c1] = colorPairForAudioIndex(audioIndex);
  const file = layer.evidenceLabel;

  return layer.bundle.traces.map((trace, traceIdx) => {
    const x = normalizePlotArray(trace.x);
    const y = normalizePlotArray(trace.y);
    const baseName = trace.name?.trim() || "série";
    const origColor = trace.line?.color;
    const width = trace.line?.width ?? 2;

    if (!compareMode) {
      return {
        type: trace.type || "scatter",
        mode: trace.mode || "lines",
        x,
        y,
        name: baseName,
        line: { color: origColor || c0, width },
        hovertemplate:
          trace.hovertemplate ||
          `${baseName}<br>%{x}<br>%{y}<extra></extra>`,
      };
    }

    const color =
      layer.bundle.traces.length > 1 ? (traceIdx % 2 === 0 ? c0 : c1) : c0;
    const legendLabel =
      layer.bundle.traces.length > 1
        ? `Áudio ${audioIndex + 1} — ${shortTraceLabel(baseName)}`
        : `Áudio ${audioIndex + 1}`;
    const hoverName = `${legendLabel} — ${file}`;

    return {
      type: trace.type || "scatter",
      mode: trace.mode || "lines",
      x,
      y,
      name: legendLabel,
      line: { color, width },
      hovertemplate:
        trace.hovertemplate?.replace("<extra>", "") ||
        `${hoverName}<br>%{x}<br>%{y}<extra></extra>`,
      meta: { file, series: shortTraceLabel(baseName) },
    };
  });
}

export function flattenOverlayTraces(
  layers: AudioOverlayLayer[],
  compareMode: boolean
): PlotTraceJson[] {
  return layers.flatMap((layer, idx) => tracesForOverlayLayer(layer, idx, compareMode));
}

export function emptyLtasOverlays(): Record<LtasPanelKey, AudioOverlayLayer[]> {
  return { normal: [], "6db": [], sorted: [], derivative: [] };
}

export function appendOverlayLayer(
  previous: AudioOverlayLayer[],
  retain: boolean,
  evidenceLabel: string,
  bundle: PlotBundleJson
): AudioOverlayLayer[] {
  const layer: AudioOverlayLayer = { evidenceLabel, bundle };
  if (!retain || previous.length === 0) {
    return [layer];
  }
  return [...previous, layer];
}

export function appendLtasOverlays(
  previous: Record<LtasPanelKey, AudioOverlayLayer[]>,
  retain: boolean,
  evidenceLabel: string,
  panels: Record<LtasPanelKey, PlotBundleJson>
): Record<LtasPanelKey, AudioOverlayLayer[]> {
  const next = { ...previous };
  for (const { key } of LTAS_PANELS) {
    const bundle = panels[key];
    if (!bundle) continue;
    next[key] = appendOverlayLayer(previous[key] ?? [], retain, evidenceLabel, bundle);
  }
  return next;
}
