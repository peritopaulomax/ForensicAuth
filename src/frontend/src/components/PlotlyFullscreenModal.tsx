import { useCallback, useEffect, type CSSProperties, type ReactNode } from "react";

export function plotlyFullscreenHeight(): number {
  if (typeof window === "undefined") return 720;
  return Math.max(480, Math.round(window.innerHeight * 0.85));
}

interface PlotlyFullscreenModalProps {
  title?: string;
  onClose: () => void;
  children: ReactNode;
}

export default function PlotlyFullscreenModal({ title, onClose, children }: PlotlyFullscreenModalProps) {
  const handleKey = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    },
    [onClose]
  );

  useEffect(() => {
    document.addEventListener("keydown", handleKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", handleKey);
      document.body.style.overflow = prev;
    };
  }, [handleKey]);

  return (
    <div
      role="dialog"
      aria-modal
      aria-labelledby={title ? "plotly-fullscreen-title" : undefined}
      aria-label={title ? undefined : "Gráfico em tela cheia"}
      style={backdropStyle}
      onClick={onClose}
    >
      <div style={panelStyle} onClick={(e) => e.stopPropagation()}>
        <div style={headerStyle}>
          <h3 id="plotly-fullscreen-title" style={titleStyle}>
            {title || "Gráfico interativo"}
          </h3>
          <button
            type="button"
            onClick={onClose}
            aria-label="Fechar tela cheia"
            style={closeBtnStyle}
          >
            ×
          </button>
        </div>
        <div style={bodyStyle}>{children}</div>
      </div>
    </div>
  );
}

const backdropStyle: CSSProperties = {
  position: "fixed",
  inset: 0,
  background: "rgba(0,0,0,0.62)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  zIndex: 2000,
  padding: "0.5rem",
};

const panelStyle: CSSProperties = {
  background: "#fff",
  borderRadius: 10,
  width: "min(98vw, 1400px)",
  height: "min(95vh, 960px)",
  maxWidth: "98vw",
  maxHeight: "95vh",
  display: "flex",
  flexDirection: "column",
  boxShadow: "0 24px 48px rgba(0,0,0,0.28)",
  overflow: "hidden",
};

const headerStyle: CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  padding: "0.5rem 0.75rem",
  borderBottom: "1px solid #e5e7eb",
  flexShrink: 0,
};

const titleStyle: CSSProperties = {
  margin: 0,
  fontSize: "1rem",
  fontWeight: 600,
  color: "#1a1a2e",
};

const closeBtnStyle: CSSProperties = {
  background: "none",
  border: "none",
  fontSize: "1.5rem",
  lineHeight: 1,
  cursor: "pointer",
  color: "#6b7280",
  padding: "0.15rem 0.4rem",
};

const bodyStyle: CSSProperties = {
  flex: 1,
  minHeight: 0,
  padding: "0.5rem 0.75rem 0.75rem",
  display: "flex",
  flexDirection: "column",
  overflow: "hidden",
};
