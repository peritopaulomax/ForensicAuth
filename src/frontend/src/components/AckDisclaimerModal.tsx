interface Props {
  open: boolean;
  title: string;
  body: string;
  onConfirm: () => void;
  confirmLabel?: string;
  titleId?: string;
  testId?: string;
  confirmTestId?: string;
}

const overlayStyle: React.CSSProperties = {
  position: "fixed",
  inset: 0,
  background: "rgba(15, 23, 42, 0.45)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  zIndex: 1100,
  padding: "1rem",
};

const panelStyle: React.CSSProperties = {
  background: "#fff",
  borderRadius: "10px",
  padding: "1.4rem 1.5rem",
  maxWidth: "560px",
  width: "100%",
  boxShadow: "0 12px 40px rgba(0,0,0,0.18)",
};

/** Modal de aviso com aceite explícito (OK). Clique fora não fecha. */
export default function AckDisclaimerModal({
  open,
  title,
  body,
  onConfirm,
  confirmLabel = "OK, entendi",
  titleId = "ack-disclaimer-title",
  testId = "ack-disclaimer-modal",
  confirmTestId = "ack-disclaimer-ok",
}: Props) {
  if (!open) return null;

  return (
    <div style={overlayStyle} role="presentation">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        style={panelStyle}
        data-testid={testId}
      >
        <h2
          id={titleId}
          style={{ margin: "0 0 0.75rem", fontSize: "1.05rem", color: "#1e293b", fontWeight: 650 }}
        >
          {title}
        </h2>
        {(body || "")
          .split(/\n\n+/)
          .map((para) => para.trim())
          .filter(Boolean)
          .map((para, index, arr) => (
            <p
              key={index}
              style={{
                margin: index < arr.length - 1 ? "0 0 0.75rem" : "0 0 1.25rem",
                fontSize: "0.9rem",
                color: "#334155",
                lineHeight: 1.55,
              }}
            >
              {para}
            </p>
          ))}
        <div style={{ display: "flex", justifyContent: "flex-end" }}>
          <button
            type="button"
            onClick={onConfirm}
            data-testid={confirmTestId}
            style={{
              padding: "0.55rem 1.15rem",
              background: "#0369a1",
              color: "#fff",
              border: "none",
              borderRadius: "6px",
              cursor: "pointer",
              fontSize: "0.88rem",
              fontWeight: 600,
            }}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
