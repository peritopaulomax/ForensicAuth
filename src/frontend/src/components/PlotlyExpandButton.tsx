import type { CSSProperties } from "react";

const btnStyle: CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  gap: "0.35rem",
  padding: "0.35rem 0.55rem",
  background: "#f3f4f6",
  border: "1px solid #d1d5db",
  borderRadius: 6,
  cursor: "pointer",
  color: "#374151",
  fontSize: "0.8rem",
  lineHeight: 1,
};

function MaximizeIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"
      />
    </svg>
  );
}

interface PlotlyExpandButtonProps {
  onClick: () => void;
  /** Rótulo acessível (PT-BR). */
  ariaLabel?: string;
}

export default function PlotlyExpandButton({
  onClick,
  ariaLabel = "Abrir gráfico em tela cheia",
}: PlotlyExpandButtonProps) {
  return (
    <button type="button" onClick={onClick} aria-label={ariaLabel} title={ariaLabel} style={btnStyle}>
      <MaximizeIcon />
    </button>
  );
}
