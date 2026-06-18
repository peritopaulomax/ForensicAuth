/** Plotly interativo gerado no backend. */

import PlotlyChartFrame from "@/components/PlotlyChartFrame";

interface PlotlyHtmlFrameProps {
  url: string | null;
  title?: string;
  height?: number;
}

const iframeBaseStyle = {
  width: "100%",
  border: "none",
  borderRadius: 8,
  background: "#fff",
  display: "block",
} as const;

const chartShellStyle = {
  width: "100%",
  display: "flex",
  flexDirection: "column" as const,
  border: "1px solid #e5e7eb",
  borderRadius: 8,
  overflow: "hidden",
  background: "#fff",
};

export default function PlotlyHtmlFrame({ url, title, height = 500 }: PlotlyHtmlFrameProps) {
  if (!url) return null;

  const iframeTitle = title || "Gráfico interativo";

  return (
    <PlotlyChartFrame
      title={title}
      fullscreenContent={
        <div style={{ ...chartShellStyle, flex: 1, minHeight: 0, height: "100%" }}>
          <iframe title={iframeTitle} src={url} style={{ ...iframeBaseStyle, flex: 1, minHeight: 0, height: "100%" }} />
        </div>
      }
    >
      <div style={{ ...chartShellStyle, height }}>
        <iframe title={iframeTitle} src={url} style={{ ...iframeBaseStyle, height: "100%", minHeight: height }} />
      </div>
    </PlotlyChartFrame>
  );
}
