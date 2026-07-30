/**
 * Renderização segura de relatórios Markdown (sem HTML cru / sem rehype-raw).
 */
import type { CSSProperties } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

type Props = {
  content: string;
  loading?: boolean;
  maxHeight?: number | string;
  emptyLabel?: string;
};

export default function MarkdownReportView({
  content,
  loading = false,
  maxHeight = 520,
  emptyLabel = "(sem conteudo)",
}: Props) {
  if (loading) {
    return (
      <div style={{ ...boxStyle, maxHeight }}>
        <p style={{ margin: 0, color: "#6b7280", fontSize: "0.88rem" }}>Carregando…</p>
      </div>
    );
  }

  const text = (content || "").trim();
  if (!text) {
    return (
      <div style={{ ...boxStyle, maxHeight }}>
        <p style={{ margin: 0, color: "#6b7280", fontSize: "0.88rem" }}>{emptyLabel}</p>
      </div>
    );
  }

  return (
    <div style={{ ...boxStyle, maxHeight }} className="fa-md-report">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children }) => <h1 style={h1Style}>{children}</h1>,
          h2: ({ children }) => <h2 style={h2Style}>{children}</h2>,
          h3: ({ children }) => <h3 style={h3Style}>{children}</h3>,
          h4: ({ children }) => <h4 style={h4Style}>{children}</h4>,
          p: ({ children }) => <p style={pStyle}>{children}</p>,
          ul: ({ children }) => <ul style={listStyle}>{children}</ul>,
          ol: ({ children }) => <ol style={listStyle}>{children}</ol>,
          li: ({ children }) => <li style={{ marginBottom: "0.25rem" }}>{children}</li>,
          blockquote: ({ children }) => <blockquote style={quoteStyle}>{children}</blockquote>,
          code: ({ className, children, ...props }) => {
            // Só bloco se for fence (className language-*) ou multilinha.
            // NÃO usar length: hashes SHA-512 cabem em `inline` e ficariam
            // com cor clara (#e2e8f0) sobre o fundo do relatório.
            const raw = String(children ?? "");
            const isBlock = Boolean(className) || raw.includes("\n");
            if (!isBlock) {
              return (
                <code style={inlineCodeStyle} {...props}>
                  {children}
                </code>
              );
            }
            return (
              <code style={blockCodeInnerStyle} className={className} {...props}>
                {children}
              </code>
            );
          },
          pre: ({ children }) => <pre style={preStyle}>{children}</pre>,
          table: ({ children }) => (
            <div style={{ overflowX: "auto", margin: "0.75rem 0" }}>
              <table style={tableStyle}>{children}</table>
            </div>
          ),
          thead: ({ children }) => <thead style={{ background: "#f1f5f9" }}>{children}</thead>,
          th: ({ children }) => <th style={thStyle}>{children}</th>,
          td: ({ children }) => <td style={tdStyle}>{children}</td>,
          a: ({ href, children }) => (
            <a href={href} style={linkStyle} target="_blank" rel="noopener noreferrer">
              {children}
            </a>
          ),
          hr: () => <hr style={hrStyle} />,
          strong: ({ children }) => <strong style={{ fontWeight: 650 }}>{children}</strong>,
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}

const boxStyle: CSSProperties = {
  overflow: "auto",
  border: "1px solid #e5e7eb",
  borderRadius: 8,
  background: "#fafbfc",
  padding: "0.85rem 1.1rem 1.1rem",
  color: "#1e293b",
  fontSize: "0.88rem",
  lineHeight: 1.55,
};

const h1Style: CSSProperties = {
  margin: "0 0 0.75rem",
  fontSize: "1.25rem",
  fontWeight: 700,
  color: "#0f172a",
  borderBottom: "1px solid #e2e8f0",
  paddingBottom: "0.45rem",
};

const h2Style: CSSProperties = {
  margin: "1.35rem 0 0.55rem",
  fontSize: "1.05rem",
  fontWeight: 700,
  color: "#0f172a",
};

const h3Style: CSSProperties = {
  margin: "1.1rem 0 0.4rem",
  fontSize: "0.95rem",
  fontWeight: 650,
  color: "#1e293b",
};

const h4Style: CSSProperties = {
  margin: "0.9rem 0 0.35rem",
  fontSize: "0.9rem",
  fontWeight: 650,
  color: "#334155",
};

const pStyle: CSSProperties = {
  margin: "0.45rem 0",
};

const listStyle: CSSProperties = {
  margin: "0.4rem 0 0.6rem",
  paddingLeft: "1.25rem",
};

const quoteStyle: CSSProperties = {
  margin: "0.75rem 0",
  padding: "0.55rem 0.85rem",
  borderLeft: "3px solid #94a3b8",
  background: "#f1f5f9",
  color: "#334155",
  borderRadius: "0 6px 6px 0",
};

const inlineCodeStyle: CSSProperties = {
  fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
  fontSize: "0.82em",
  background: "#e2e8f0",
  color: "#0f172a",
  padding: "0.1rem 0.35rem",
  borderRadius: 4,
};

const preStyle: CSSProperties = {
  margin: "0.65rem 0",
  padding: "0.75rem 0.9rem",
  background: "#0f172a",
  color: "#e2e8f0",
  borderRadius: 6,
  overflowX: "auto",
  fontSize: "0.78rem",
  lineHeight: 1.45,
};

const blockCodeInnerStyle: CSSProperties = {
  fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
  background: "transparent",
  color: "#e2e8f0",
  padding: 0,
  display: "block",
  whiteSpace: "pre-wrap",
  wordBreak: "break-word",
};

const tableStyle: CSSProperties = {
  width: "100%",
  borderCollapse: "collapse",
  fontSize: "0.82rem",
  minWidth: 420,
};

const thStyle: CSSProperties = {
  textAlign: "left",
  padding: "0.45rem 0.55rem",
  border: "1px solid #cbd5e1",
  fontWeight: 650,
  color: "#0f172a",
  verticalAlign: "top",
};

const tdStyle: CSSProperties = {
  padding: "0.4rem 0.55rem",
  border: "1px solid #e2e8f0",
  verticalAlign: "top",
  color: "#1e293b",
};

const linkStyle: CSSProperties = {
  color: "#1d4ed8",
  textDecoration: "underline",
};

const hrStyle: CSSProperties = {
  border: "none",
  borderTop: "1px solid #e2e8f0",
  margin: "1rem 0",
};
