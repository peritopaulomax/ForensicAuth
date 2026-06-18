/**
 * Legenda da escala RdBu_r usada no heatmap TruFor (matplotlib).
 * Baixo (azul) = autêntico · Alto (vermelho) = manipulado.
 */

const RD_BU_R_STOPS = [
  "#053061",
  "#2166AC",
  "#4393C3",
  "#92C5DE",
  "#D1E5F0",
  "#F7F7F7",
  "#FDDBC7",
  "#F4A582",
  "#D6604D",
  "#B2182B",
  "#67001F",
] as const;

const GRADIENT = RD_BU_R_STOPS.map((color, i) => {
  const pct = (i / (RD_BU_R_STOPS.length - 1)) * 100;
  return `${color} ${pct}%`;
}).join(", ");

const TICKS = [0, 0.25, 0.5, 0.75, 1] as const;

type Props = {
  /** Texto curto abaixo da barra (ex.: overlay usa a mesma escala). */
  caption?: string;
};

export default function TruForHeatmapColorScale({ caption }: Props) {
  return (
    <div
      data-testid="trufor-heatmap-color-scale"
      style={{
        marginBottom: "0.75rem",
        padding: "0.55rem 0.65rem",
        background: "#f8fafc",
        border: "1px solid #e2e8f0",
        borderRadius: 6,
        maxWidth: 420,
      }}
    >
      <p style={{ margin: "0 0 0.4rem", fontSize: "0.78rem", color: "#374151", fontWeight: 600 }}>
        Escala de localização (RdBu)
      </p>
      <div
        aria-hidden
        style={{
          height: 14,
          borderRadius: 3,
          border: "1px solid #cbd5e1",
          background: `linear-gradient(to right, ${GRADIENT})`,
        }}
      />
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          marginTop: 4,
          fontSize: "0.72rem",
          color: "#64748b",
          fontVariantNumeric: "tabular-nums",
        }}
      >
        {TICKS.map((t) => (
          <span key={t}>{t.toFixed(2)}</span>
        ))}
      </div>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          marginTop: 2,
          fontSize: "0.72rem",
          color: "#475569",
        }}
      >
        <span style={{ color: "#2166AC" }}>0 — autêntico</span>
        <span style={{ color: "#94a3b8" }}>0.5 — ambíguo</span>
        <span style={{ color: "#B2182B" }}>1 — manipulado</span>
      </div>
      {caption && (
        <p style={{ margin: "0.4rem 0 0", fontSize: "0.72rem", color: "#6b7280" }}>{caption}</p>
      )}
    </div>
  );
}
