import { useMemo } from "react";
import JpegMatrixLegendCompact from "@/components/jpeg/JpegMatrixLegendCompact";
import { buildMatrixDisplayLabels } from "@/utils/jpegMatrixAliases";
import type { JpegStructureMatrixPayload } from "@/utils/jpegStructureMatrix";

export default function JpegStructureMatchMatrix({ data }: { data: JpegStructureMatrixPayload }) {
  const matrix = data.matrix;
  const display = useMemo(() => buildMatrixDisplayLabels(data), [data]);

  if (!matrix?.rows?.length) {
    return <p style={{ fontSize: "0.85rem", color: "#6b7280" }}>Matriz vazia.</p>;
  }

  const rowHeader = data.mode === "with_reference" ? "Padrão" : "Linha";

  return (
    <div className="jpeg-matrix-wrap">
      <JpegMatrixLegendCompact legend={display.legend} />

      <div className="jpeg-compare-legend" style={{ marginBottom: "0.65rem" }}>
        <span className="jpeg-compare-legend__item jpeg-compare-legend__item--match">Convergente</span>
        <span className="jpeg-compare-legend__item jpeg-compare-legend__item--diverge">Divergente</span>
        <span className="jpeg-compare-legend__hint">
          Critério: marcadores, DQT e thumbnails APP (DHT só posição/tipo)
        </span>
      </div>

      <div className="jpeg-matrix-scroll">
        <table className="jpeg-matrix">
          <thead>
            <tr>
              <th className="jpeg-matrix__corner">{rowHeader}</th>
              {display.colAliases.map((alias, i) => (
                <th key={`col-${i}`} className="jpeg-matrix__col-head" title={matrix.col_labels[i]}>
                  {alias}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {matrix.rows.map((row, rowIdx) => (
              <tr key={`row-${row.row_index}`}>
                <th className="jpeg-matrix__row-head" title={row.label}>
                  {display.rowAliases[rowIdx] ?? `R${rowIdx + 1}`}
                </th>
                {matrix.col_labels.map((_, colIdx) => {
                  const cell = row.cells[colIdx];
                  if (!cell) {
                    return (
                      <td key={`cell-${row.row_index}-${colIdx}`} className="jpeg-matrix__cell jpeg-matrix__cell--empty">
                        —
                      </td>
                    );
                  }
                  const cls = cell.unavailable
                    ? "jpeg-matrix__cell--diverge"
                    : cell.matches
                      ? "jpeg-matrix__cell--match"
                      : "jpeg-matrix__cell--diverge";
                  const title = cell.unavailable
                    ? String(cell.reason || "Indisponível")
                    : cell.matches
                      ? "Convergente"
                      : String(cell.reason || "Divergente");
                  const symbol = cell.unavailable ? "?" : cell.matches ? "✓" : "✗";
                  return (
                    <td
                      key={`cell-${row.row_index}-${colIdx}`}
                      className={`jpeg-matrix__cell ${cls}`}
                      title={title}
                      data-testid="jpeg-matrix-cell"
                    >
                      {symbol}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
