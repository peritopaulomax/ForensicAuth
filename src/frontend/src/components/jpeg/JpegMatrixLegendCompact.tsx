import type { MatrixLegendEntry } from "@/utils/jpegMatrixAliases";

export default function JpegMatrixLegendCompact({ legend }: { legend: MatrixLegendEntry[] }) {
  const references = legend.filter((e) => e.role === "reference");
  const questioned = legend.filter((e) => e.role === "questioned");

  if (legend.length === 0) return null;

  return (
    <div className="jpeg-matrix-legend-compact" data-testid="jpeg-matrix-legend">
      {references.length > 0 && (
        <LegendSection title="Padrões" count={references.length} entries={references} />
      )}
      {questioned.length > 0 && (
        <LegendSection
          title={references.length > 0 ? "Questionados" : "Arquivos"}
          count={questioned.length}
          entries={questioned}
          wide={references.length === 0 || questioned.length > 12}
        />
      )}
    </div>
  );
}

function LegendSection({
  title,
  count,
  entries,
  wide = false,
}: {
  title: string;
  count: number;
  entries: MatrixLegendEntry[];
  wide?: boolean;
}) {
  return (
    <section className={`jpeg-matrix-legend-compact__section${wide ? " is-wide" : ""}`}>
      <h4 className="jpeg-matrix-legend-compact__title">
        {title} <span className="jpeg-matrix-legend-compact__count">({count})</span>
      </h4>
      <ul className="jpeg-matrix-legend-compact__list">
        {entries.map((entry) => (
          <li key={`${entry.role}-${entry.alias}`} title={entry.label}>
            <span className="jpeg-matrix-legend-compact__alias">{entry.alias}</span>
            <span className="jpeg-matrix-legend-compact__file">{entry.label}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
