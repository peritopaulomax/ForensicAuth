import { useMemo, useState, type CSSProperties } from "react";

export interface MetadataTag {
  tag: string;
  value: string;
  hint?: string;
  group?: string;
  source?: string;
  family?: string;
}

export default function MetadataTagTable({
  entries,
  emptyMessage = "Nenhum campo nesta categoria.",
  showHints = false,
  hintLayout = "auto",
}: {
  entries: MetadataTag[];
  emptyMessage?: string;
  showHints?: boolean;
  /** auto = coluna em telas largas, abaixo do valor em estreito; stacked = sempre abaixo */
  hintLayout?: "auto" | "column" | "stacked";
}) {
  const [filter, setFilter] = useState("");
  const hasHints = showHints || entries.some((e) => Boolean(e.hint));
  const hasSource = entries.some((e) => e.source);
  const useStackedHints = hintLayout === "stacked" || (hintLayout === "auto" && hasHints);

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return entries;
    return entries.filter(
      (e) =>
        e.tag.toLowerCase().includes(q) ||
        e.value.toLowerCase().includes(q) ||
        (e.hint || "").toLowerCase().includes(q)
    );
  }, [entries, filter]);

  if (!entries.length) {
    return <p style={{ color: "#9ca3af", fontSize: "0.85rem", margin: 0 }}>{emptyMessage}</p>;
  }

  return (
    <div className={useStackedHints ? "metadata-tag-table--stacked" : undefined}>
      <input
        type="search"
        placeholder="Filtrar tags ou valores…"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        className="metadata-tag-table__search"
        style={{
          width: "100%",
          maxWidth: 360,
          marginBottom: "0.75rem",
          padding: "0.45rem 0.65rem",
          border: "1px solid #e5e7eb",
          borderRadius: 6,
          fontSize: "0.85rem",
        }}
      />
      <div style={{ maxHeight: 480, overflow: "auto", border: "1px solid #e5e7eb", borderRadius: 6 }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.8rem" }}>
          <thead>
            <tr style={{ background: "#f3f4f6", position: "sticky", top: 0 }}>
              <th style={thStyle}>Tag</th>
              <th style={thStyle}>Valor</th>
              {hasHints && !useStackedHints && <th style={thStyle}>Significado</th>}
              {hasSource && !useStackedHints && <th style={thStyle}>Fonte</th>}
            </tr>
          </thead>
          <tbody>
            {filtered.map((e, i) => (
              <tr key={`${e.tag}-${i}`} style={{ borderTop: "1px solid #f3f4f6" }}>
                <td style={{ ...tdStyle, fontFamily: "monospace", color: "#1e40af", whiteSpace: "nowrap" }}>
                  {e.tag}
                </td>
                <td className="metadata-tag-table__value-cell" style={{ ...tdStyle, wordBreak: "break-word" }}>
                  {e.value}
                  {useStackedHints && e.hint && <span className="metadata-tag-table__hint-below">{e.hint}</span>}
                  {useStackedHints && hasSource && e.source && (
                    <span className="metadata-tag-table__source">fonte: {e.source}</span>
                  )}
                </td>
                {hasHints && !useStackedHints && (
                  <td style={{ ...tdStyle, color: "#6b7280", fontSize: "0.75rem" }}>{e.hint || "—"}</td>
                )}
                {hasSource && !useStackedHints && (
                  <td style={{ ...tdStyle, color: "#6b7280", fontSize: "0.72rem" }}>{e.source || "—"}</td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {filtered.length === 0 && (
        <p style={{ color: "#9ca3af", fontSize: "0.85rem", marginTop: "0.5rem" }}>Nenhum resultado para o filtro.</p>
      )}
    </div>
  );
}

const thStyle: CSSProperties = {
  textAlign: "left",
  padding: "0.5rem 0.65rem",
  fontWeight: 600,
  color: "#374151",
};

const tdStyle: CSSProperties = {
  padding: "0.45rem 0.65rem",
  verticalAlign: "top",
};
