import type { CSSProperties } from "react";

export interface ForensicInsight {
  severity: "high" | "medium" | "info" | string;
  title: string;
  detail: string;
  tags?: string[];
}

const SEVERITY_LABEL: Record<string, string> = {
  high: "Alto",
  medium: "Médio",
  info: "Info",
};

export default function ForensicInsightsPanel({ insights }: { insights: ForensicInsight[] }) {
  if (!insights.length) return null;

  return (
    <div>
      <h4 style={{ fontSize: "0.9rem", margin: "0 0 0.65rem", color: "#1a1a2e" }}>Alertas automáticos</h4>
      <div className="metadata-alert-list">
        {insights.map((item, i) => {
          const sev = item.severity in SEVERITY_LABEL ? item.severity : "info";
          return (
            <div key={`${item.title}-${i}`} className={`metadata-alert metadata-alert--${sev}`}>
              <div className="metadata-alert__head">
                <span className="metadata-alert__severity">{SEVERITY_LABEL[sev] || "Info"}</span>
                <span className="metadata-alert__title">{item.title}</span>
              </div>
              <p className="metadata-alert__detail">{item.detail}</p>
              {item.tags && item.tags.length > 0 && (
                <div style={{ marginTop: "0.35rem", display: "flex", flexWrap: "wrap", gap: "0.3rem" }}>
                  {item.tags.slice(0, 8).map((tag) => (
                    <code key={tag} style={tagChipStyle}>
                      {tag}
                    </code>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

const tagChipStyle: CSSProperties = {
  fontSize: "0.68rem",
  background: "#f9fafb",
  border: "1px solid #e5e7eb",
  borderRadius: 4,
  padding: "0.1rem 0.35rem",
  color: "#4b5563",
};
