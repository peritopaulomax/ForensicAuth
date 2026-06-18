import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";
import PlotlyChartFrame from "@/components/PlotlyChartFrame";
import { plotlyFullscreenHeight } from "@/components/PlotlyFullscreenModal";
import { flattenOverlayTraces, type AudioOverlayLayer } from "@/lib/audioComparison";
import { buildForensicLayout, PLOTLY_FORENSIC_CONFIG } from "@/lib/plotlyForensicTheme";

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

export interface AudioOverlayPlotHandle {
  exportPngBlob(): Promise<Blob>;
}

interface AudioOverlayPlotProps {
  layers: AudioOverlayLayer[];
  /** Título único (evita duplicar layout_title do backend). */
  panelTitle?: string;
  height?: number;
  /** Largura fixa opcional; omitir para preencher 100% do container (LTAS, etc.). */
  width?: number;
  /** Quando false, omite botão de tela cheia (uso interno no modal). */
  enableFullscreen?: boolean;
}

function AudioOverlayPlotCanvas({
  layers,
  panelTitle,
  height = 500,
  width,
  divRef,
}: AudioOverlayPlotProps & { divRef: React.RefObject<HTMLDivElement | null> }) {
  const [plotlyReady, setPlotlyReady] = useState(!!window.Plotly);

  const compareCount = layers.length;
  const plotTraces = useMemo(
    () => flattenOverlayTraces(layers, compareCount > 1),
    [layers, compareCount]
  );

  const bundle = layers[0]?.bundle;
  const layout = useMemo(
    () =>
      buildForensicLayout({
        panelTitle: panelTitle || undefined,
        xaxisTitle: bundle?.xaxis_title,
        yaxisTitle: bundle?.yaxis_title,
        width,
        height,
        traceCount: plotTraces.length,
        compareCount,
        showLegend: compareCount > 1 || plotTraces.length > 1,
      }),
    [bundle, panelTitle, width, height, plotTraces.length, compareCount]
  );

  const plotKey = useMemo(
    () =>
      `${compareCount}-${plotTraces.length}-${plotTraces.map((t) => t.name).join("|")}`,
    [compareCount, plotTraces]
  );

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
    const el = divRef.current;
    return () => {
      if (el && window.Plotly) window.Plotly.purge(el);
    };
  }, [divRef]);

  useEffect(() => {
    if (!plotlyReady || !divRef.current || !window.Plotly || plotTraces.length === 0) return;
    const el = divRef.current;
    window.Plotly.react(el, plotTraces, layout, PLOTLY_FORENSIC_CONFIG)
      .then(() => window.Plotly?.Plots.resize(el))
      .catch(() => undefined);
  }, [plotlyReady, plotKey, plotTraces, layout, divRef]);

  useEffect(() => {
    const el = divRef.current;
    if (!el || !plotlyReady || !window.Plotly) return;
    const ro = new ResizeObserver(() => {
      window.Plotly?.Plots.resize(el);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [plotlyReady, plotKey, divRef]);

  return (
    <div
      ref={divRef as React.RefObject<HTMLDivElement>}
      style={{
        width: "100%",
        height,
        flex: 1,
        minHeight: 0,
        border: "1px solid #e5e7eb",
        borderRadius: 8,
        background: "#fff",
        overflow: "hidden",
      }}
    />
  );
}

const AudioOverlayPlot = forwardRef<AudioOverlayPlotHandle, AudioOverlayPlotProps>(function AudioOverlayPlot(
  { layers, panelTitle, height = 500, width, enableFullscreen = true },
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

  if (layers.length === 0) return null;

  const canvas = (
    <AudioOverlayPlotCanvas
      layers={layers}
      panelTitle={panelTitle}
      height={height}
      width={width}
      divRef={divRef}
    />
  );

  if (!enableFullscreen) {
    return canvas;
  }

  const fsHeight = plotlyFullscreenHeight();

  return (
    <PlotlyChartFrame
      title={panelTitle}
      fullscreenContent={
        <AudioOverlayPlotCanvas layers={layers} panelTitle={panelTitle} height={fsHeight} divRef={divRef} />
      }
    >
      {canvas}
    </PlotlyChartFrame>
  );
});

export default AudioOverlayPlot;
