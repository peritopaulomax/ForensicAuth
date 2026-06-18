/** Legenda do mapa de confiança TruFor (0–1, escala de cinza). */

const TICKS = [0, 0.25, 0.5, 0.75, 1] as const;

export default function TruForConfidenceColorScale() {
  return (
    <div
      data-testid="trufor-confidence-color-scale"
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
        Escala de confiança da localização
      </p>
      <div
        aria-hidden
        style={{
          height: 14,
          borderRadius: 3,
          border: "1px solid #cbd5e1",
          background: "linear-gradient(to right, #000000, #ffffff)",
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
        <span>0 — baixa confiança</span>
        <span>1 — alta confiança</span>
      </div>
    </div>
  );
}
