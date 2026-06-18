import type { ReactNode } from "react";

interface Props {
  title: string;
  children: ReactNode;
}

/** Painel visual que agrupa cards de técnicas na aba Imagem. */
export default function ImageAnalysisGroupPanel({ title, children }: Props) {
  return (
    <section
      style={{
        background: "linear-gradient(180deg, #f8fafc 0%, #ffffff 55%)",
        border: "1px solid #e2e8f0",
        borderRadius: "14px",
        padding: "1.35rem 1.5rem 1.5rem",
        boxShadow: "0 1px 2px rgba(15, 23, 42, 0.04), 0 4px 16px rgba(15, 23, 42, 0.03)",
      }}
    >
      <header
        style={{
          display: "flex",
          alignItems: "center",
          gap: "0.65rem",
          marginBottom: "1.1rem",
          paddingBottom: "0.85rem",
          borderBottom: "1px solid #e5e7eb",
        }}
      >
        <span
          aria-hidden
          style={{
            width: 4,
            alignSelf: "stretch",
            minHeight: 20,
            borderRadius: 4,
            background: "linear-gradient(180deg, #0369a1 0%, #1a1a2e 100%)",
            flexShrink: 0,
          }}
        />
        <h3
          style={{
            margin: 0,
            fontSize: "0.95rem",
            fontWeight: 600,
            color: "#1e293b",
            lineHeight: 1.35,
            letterSpacing: "0.01em",
          }}
        >
          {title}
        </h3>
      </header>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))",
          gap: "0.85rem",
        }}
      >
        {children}
      </div>
    </section>
  );
}
