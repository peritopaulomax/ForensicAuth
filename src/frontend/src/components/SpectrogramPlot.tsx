import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
  type RefObject,
} from "react";
import PlotlyChartFrame from "@/components/PlotlyChartFrame";
import { plotlyFullscreenHeight } from "@/components/PlotlyFullscreenModal";
import {
  applySpectrogramDisplayOptions,
  type SpectrogramDecimationMeta,
} from "@/lib/spectrogramDecimate";
import { PLOTLY_FORENSIC_CONFIG } from "@/lib/plotlyForensicTheme";

export const DEFAULT_SPECTROGRAM_COLORSCALE = "Electric" as const;

/** Paletas Plotly usadas em analise forense de espectrograma. */
export const SPECTROGRAM_COLORSCALES = [
  { id: "Electric", label: "Electric (padrão)" },
  { id: "Viridis", label: "Viridis" },
  { id: "Plasma", label: "Plasma" },
  { id: "Inferno", label: "Inferno" },
  { id: "Magma", label: "Magma" },
  { id: "Cividis", label: "Cividis" },
  { id: "Turbo", label: "Turbo" },
  { id: "Hot", label: "Hot" },
  { id: "Jet", label: "Jet" },
  { id: "Greys", label: "Escala de cinza" },
  { id: "Portland", label: "Portland" },
  { id: "Blackbody", label: "Blackbody" },
  { id: "Bluered", label: "Azul–vermelho" },
  { id: "RdBu", label: "RdBu" },
  { id: "Picnic", label: "Picnic" },
] as const;

export type SpectrogramColorscale = (typeof SPECTROGRAM_COLORSCALES)[number]["id"];

export interface SpectrogramFullData {
  times: number[];
  frequencies: number[];
  magnitude_db: number[][];
  sample_rate: number;
  n_fft: number;
  hop_length: number;
  stft_shape: [number, number];
  duration_sec: number;
  hop_adjusted: boolean;
  window_type?: string;
  window_size_percent?: number;
}

const PLOTLY_CDN = "https://cdn.plot.ly/plotly-2.27.0.min.js";

let plotlyLoadPromise: Promise<void> | null = null;

function loadPlotly(): Promise<void> {
  if (window.Plotly) return Promise.resolve();
  if (plotlyLoadPromise) return plotlyLoadPromise;
  plotlyLoadPromise = new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = PLOTLY_CDN;
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("Falha ao carregar Plotly"));
    document.head.appendChild(script);
  });
  return plotlyLoadPromise;
}

function buildLayout(
  data: SpectrogramFullData,
  meta: SpectrogramDecimationMeta,
  decimateDisplay: boolean
): Record<string, unknown> {
  const win = data.window_type ? data.window_type.charAt(0).toUpperCase() + data.window_type.slice(1) : "";
  const pct = data.window_size_percent ?? "";
  const titleParts = ["Espectrograma"];
  if (win) titleParts.push(`— ${win}`);
  if (pct) titleParts.push(`(${pct}%)`);
  if (meta.decimated && decimateDisplay) {
    const [fr, fc] = meta.full_shape;
    const [dr, dc] = meta.display_shape;
    titleParts.push(`[decimado ${fr}×${fc} → ${dr}×${dc}]`);
  }

  return {
    title: { text: titleParts.join(" "), font: { size: 14, color: "#111827" } },
    paper_bgcolor: "#ffffff",
    plot_bgcolor: "#ffffff",
    font: { family: "Segoe UI, system-ui, sans-serif", size: 12, color: "#1f2937" },
    xaxis: {
      title: "Tempo (segundos)",
      showgrid: true,
      gridcolor: "#d1d5db",
      zerolinecolor: "#9ca3af",
    },
    yaxis: {
      title: "Frequência (Hz)",
      showgrid: true,
      gridcolor: "#d1d5db",
      zerolinecolor: "#9ca3af",
    },
    margin: { l: 72, r: 48, t: 56, b: 56 },
    autosize: true,
    annotations: [
      {
        x: 0.02,
        y: 0.98,
        xref: "paper",
        yref: "paper",
        text: `FFT ${data.n_fft} | SR ${data.sample_rate} Hz | grade ${meta.display_shape[0]}×${meta.display_shape[1]}${
          meta.decimated ? ` | max-pool ${meta.col_pool_factor}×${meta.row_pool_factor}` : ""
        }${data.hop_adjusted ? " | hop ajustado" : ""}`,
        showarrow: false,
        align: "left",
        bgcolor: "rgba(255,255,255,0.85)",
        bordercolor: "#d1d5db",
        borderwidth: 1,
        font: { size: 11 },
      },
    ],
  };
}

function buildTrace(
  times: number[],
  frequencies: number[],
  magnitudeDb: number[][],
  colorscale: SpectrogramColorscale
) {
  return {
    type: "heatmap" as const,
    z: magnitudeDb,
    x: times,
    y: frequencies,
    colorscale,
    hovertemplate: "Tempo: %{x:.3f}s<br>Freq: %{y:.1f}Hz<br>Magnitude: %{z:.1f}dB<extra></extra>",
    colorbar: { title: "Magnitude (dB)" },
  };
}

export interface SpectrogramPlotHandle {
  exportPngBlob: () => Promise<Blob>;
}

interface SpectrogramPlotProps {
  data: SpectrogramFullData;
  colorscale: SpectrogramColorscale;
  decimateDisplay: boolean;
  height?: number;
  enableFullscreen?: boolean;
}

function SpectrogramPlotCanvas({
  data,
  colorscale,
  decimateDisplay,
  height = 560,
  divRef,
}: SpectrogramPlotProps & { divRef?: RefObject<HTMLDivElement | null> }) {
  const localRef = useRef<HTMLDivElement>(null);
  const plotRef = divRef ?? localRef;
  const [plotlyReady, setPlotlyReady] = useState(!!window.Plotly);
  const prevVisualKeyRef = useRef("");

  const display = useMemo(
    () =>
      applySpectrogramDisplayOptions(
        { times: data.times, frequencies: data.frequencies, magnitude_db: data.magnitude_db },
        decimateDisplay
      ),
    [data.times, data.frequencies, data.magnitude_db, decimateDisplay]
  );

  const visualKey = `${display.meta.display_shape.join("x")}-${decimateDisplay}-${colorscale}`;

  useEffect(() => {
    let cancelled = false;
    loadPlotly()
      .then(() => {
        if (!cancelled) setPlotlyReady(true);
      })
      .catch(() => {
        if (!cancelled) setPlotlyReady(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const el = plotRef.current;
    return () => {
      if (el && window.Plotly) window.Plotly.purge(el);
      prevVisualKeyRef.current = "";
    };
  }, []);

  useEffect(() => {
    if (!plotlyReady || !plotRef.current || !window.Plotly) return;

    const el = plotRef.current;
    const trace = buildTrace(display.times, display.frequencies, display.magnitude_db, colorscale);
    const layout = buildLayout(data, display.meta, decimateDisplay);
    const config = PLOTLY_FORENSIC_CONFIG;

    if (prevVisualKeyRef.current !== visualKey) {
      if (prevVisualKeyRef.current) window.Plotly.purge(el);
      prevVisualKeyRef.current = visualKey;
      window.Plotly.newPlot(el, [trace], layout, config).catch(() => undefined);
    } else {
      window.Plotly.restyle(el, { colorscale }, [0]).catch(() => undefined);
    }
  }, [plotlyReady, visualKey, colorscale, data, display, decimateDisplay]);

  return (
    <div
      ref={plotRef as RefObject<HTMLDivElement>}
      style={{
        width: "100%",
        height,
        flex: 1,
        minHeight: 0,
        border: "1px solid #e5e7eb",
        borderRadius: 8,
        background: "#fff",
      }}
    />
  );
}

const SpectrogramPlot = forwardRef<SpectrogramPlotHandle, SpectrogramPlotProps>(function SpectrogramPlot(
  { data, colorscale, decimateDisplay, height = 560, enableFullscreen = true },
  ref
) {
  const divRef = useRef<HTMLDivElement>(null);

  useImperativeHandle(ref, () => ({
    async exportPngBlob() {
      if (!divRef.current || !window.Plotly?.toImage) {
        throw new Error("Grafico nao pronto para exportacao");
      }
      const dataUrl = await window.Plotly.toImage(divRef.current, {
        format: "png",
        width: 1200,
        height: 700,
        scale: 2,
      });
      const res = await fetch(dataUrl);
      return res.blob();
    },
  }));

  const canvas = (
    <SpectrogramPlotCanvas
      data={data}
      colorscale={colorscale}
      decimateDisplay={decimateDisplay}
      height={height}
      divRef={divRef}
    />
  );

  if (!enableFullscreen) {
    return canvas;
  }

  return (
    <PlotlyChartFrame
      title="Espectrograma interativo"
      fullscreenContent={
        <SpectrogramPlotCanvas
          data={data}
          colorscale={colorscale}
          decimateDisplay={decimateDisplay}
          height={plotlyFullscreenHeight()}
        />
      }
    >
      {canvas}
    </PlotlyChartFrame>
  );
});

export default SpectrogramPlot;
