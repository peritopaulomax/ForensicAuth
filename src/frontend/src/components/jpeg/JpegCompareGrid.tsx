import { Fragment, useMemo } from "react";
import {
  markerAtPosition,
  MARKER_CELL_BG,
  ROW_BG,
  type CompareCell,
  type FileComparisonRow,
  type JpegComparePayload,
  type JpegMarkerDump,
  type JpegStructureDump,
} from "@/utils/jpegStructureCompare";
import { markerHasDqtTables } from "@/utils/jpegDqtMatrix";
import { buildCompareGridRowAliases } from "@/utils/jpegMatrixAliases";

export type DqtHoverHandlers = {
  onDqtEnter: (marker: JpegMarkerDump, el: HTMLElement) => void;
  onDqtLeave: () => void;
};

export default function JpegCompareGrid({
  data,
  expandedThumbs,
  onPromoteReference,
  onToggleThumb,
  onSelectReferencePattern,
  dqtHover,
}: {
  data: JpegComparePayload;
  expandedThumbs: Set<string>;
  onPromoteReference: (rowIndex: number) => void;
  onToggleThumb: (key: string) => void;
  onSelectReferencePattern?: (evidenceId: string) => void;
  dqtHover: DqtHoverHandlers;
}) {
  const maxPositions = data.max_positions;
  const hasSections = data.comparisons.some((r) => r.row_section === "questioned");
  const firstQuestionedIdx = data.comparisons.findIndex((r) => r.row_section === "questioned");
  const rowAliases = useMemo(() => buildCompareGridRowAliases(data), [data]);

  return (
    <div className="jpeg-compare-grid-wrap">
      <table className="jpeg-compare-grid">
        <thead>
          <tr>
            <th className="jpeg-compare-grid__alias-col">Alias</th>
            <th className="jpeg-compare-grid__file-col">Arquivo</th>
            {Array.from({ length: maxPositions }, (_, i) => (
              <th key={i} className="jpeg-compare-grid__marker-col">
                {i + 1}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.comparisons.map((row, rowIndex) => (
            <Fragment key={`${row.evidence_id || row.label}-${rowIndex}`}>
              {hasSections && rowIndex === firstQuestionedIdx && (
                <tr className="jpeg-compare-grid__section-row">
                  <td colSpan={2 + maxPositions}>Questionados (vs. padrão ativo)</td>
                </tr>
              )}
              {hasSections && rowIndex === 0 && (
                <tr className="jpeg-compare-grid__section-row">
                  <td colSpan={2 + maxPositions}>Padrões de referência — clique para ativar</td>
                </tr>
              )}
              <ComparisonRows
                row={row}
                rowIndex={rowIndex}
                rowAlias={rowAliases[rowIndex] ?? `L${rowIndex + 1}`}
                structures={data.structures}
                maxPositions={maxPositions}
                expandedThumbs={expandedThumbs}
                onPromoteReference={() => onPromoteReference(rowIndex)}
                onToggleThumb={onToggleThumb}
                onSelectReferencePattern={onSelectReferencePattern}
                dqtHover={dqtHover}
              />
            </Fragment>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function rowStatus(row: FileComparisonRow): keyof typeof ROW_BG {
  if (row.unavailable) return "unavailable";
  if (row.inactive_reference) return "inactive_ref";
  if (row.is_reference) return "reference";
  if (row.fully_matches) return "match";
  return "diverge";
}

function ComparisonRows({
  row,
  rowIndex,
  rowAlias,
  structures,
  maxPositions,
  expandedThumbs,
  onPromoteReference,
  onToggleThumb,
  onSelectReferencePattern,
  dqtHover,
}: {
  row: FileComparisonRow;
  rowIndex: number;
  rowAlias: string;
  structures: JpegStructureDump[];
  maxPositions: number;
  expandedThumbs: Set<string>;
  onPromoteReference: () => void;
  onToggleThumb: (key: string) => void;
  onSelectReferencePattern?: (evidenceId: string) => void;
  dqtHover: DqtHoverHandlers;
}) {
  const bg = ROW_BG[rowStatus(row)];
  const label = row.label || row.filename || "—";
  const isInactiveRef = Boolean(row.inactive_reference);
  const canActivateRef = isInactiveRef && row.evidence_id && onSelectReferencePattern;

  return (
    <Fragment>
      <tr
        className={[
          "jpeg-compare-grid__row",
          isInactiveRef ? "jpeg-compare-grid__row--inactive-ref" : "",
          canActivateRef ? "is-clickable" : "",
        ]
          .filter(Boolean)
          .join(" ")}
        style={{ background: bg }}
        onClick={
          canActivateRef
            ? () => onSelectReferencePattern!(row.evidence_id!)
            : undefined
        }
        onDoubleClick={!isInactiveRef && !row.row_section ? onPromoteReference : undefined}
        title={
          isInactiveRef
            ? "Clique para ativar este padrão como referência"
            : row.is_reference
              ? "Padrão de referência ativo"
              : "Duplo clique para usar como referência"
        }
      >
        <td className="jpeg-compare-grid__index">{rowAlias}</td>
        <td className="jpeg-compare-grid__filename">
          {row.is_reference && !isInactiveRef && <span className="jpeg-compare-grid__ref-badge">REF</span>}
          {isInactiveRef && <span className="jpeg-compare-grid__ref-badge jpeg-compare-grid__ref-badge--muted">PAD</span>}
          <span className="jpeg-compare-grid__name" title={label}>
            {label}
          </span>
          {!row.is_reference && !row.unavailable && (
            <span
              className={`jpeg-compare-grid__row-status ${row.fully_matches ? "is-match" : "is-diverge"}`}
            >
              {row.fully_matches ? "✓" : "✗"}
            </span>
          )}
        </td>
        {Array.from({ length: maxPositions }, (_, pos) =>
          isInactiveRef ? (
            <td key={pos} className="jpeg-compare-grid__marker-cell jpeg-compare-grid__marker-cell--inactive">
              —
            </td>
          ) : (
            <MarkerCell
              key={pos}
              cell={row.cells[pos]}
              marker={markerAtPosition(structures, row.evidence_id, pos)}
              rowKey={`${row.evidence_id}-${rowIndex}`}
              pos={pos}
              expandedThumbs={expandedThumbs}
              onToggleThumb={onToggleThumb}
              dqtHover={dqtHover}
            />
          )
        )}
      </tr>
      {row.cells.map((cell, pos) => {
        if (!cell?.has_thumbnail) return null;
        const key = `${row.evidence_id}-${rowIndex}-thumb-${pos}`;
        if (!expandedThumbs.has(key)) return null;
        const appMarker = markerAtPosition(structures, row.evidence_id, pos);
        const thumbMarkers = appMarker?.thumbnail?.markers || [];
        return (
          <tr key={key} className="jpeg-compare-grid__thumb-row">
            <td />
            <td className="jpeg-compare-grid__thumb-label">↳ thumbnail {String(cell.display_name ?? "")}</td>
            {Array.from({ length: maxPositions }, (_, i) => {
              const tm = thumbMarkers[i];
              const isDqt = Boolean(tm && markerHasDqtTables(tm));
              return (
                <td key={i} className="jpeg-compare-grid__marker-cell jpeg-compare-grid__marker-cell--thumb">
                  {tm ? (
                    <span
                      className={isDqt ? "jpeg-compare-dqt-hover" : undefined}
                      data-testid={isDqt ? "dqt-thumb-cell" : undefined}
                      onMouseEnter={
                        isDqt
                          ? (e) => {
                              dqtHover.onDqtEnter(tm, e.currentTarget);
                            }
                          : undefined
                      }
                      onMouseLeave={isDqt ? dqtHover.onDqtLeave : undefined}
                    >
                      {String(tm.display_name || tm.name)}
                    </span>
                  ) : (
                    "—"
                  )}
                </td>
              );
            })}
          </tr>
        );
      })}
    </Fragment>
  );
}

function MarkerCell({
  cell,
  marker,
  rowKey,
  pos,
  expandedThumbs,
  onToggleThumb,
  dqtHover,
}: {
  cell?: CompareCell;
  marker?: JpegMarkerDump;
  rowKey: string;
  pos: number;
  expandedThumbs: Set<string>;
  onToggleThumb: (key: string) => void;
  dqtHover: DqtHoverHandlers;
}) {
  if (!cell) {
    return <td className="jpeg-compare-grid__marker-cell jpeg-compare-grid__marker-cell--empty">—</td>;
  }

  const bg = MARKER_CELL_BG[cell.status] || "#fff";
  const thumbKey = `${rowKey}-thumb-${pos}`;
  const showPlus = cell.has_thumbnail;
  const expanded = expandedThumbs.has(thumbKey);
  const isDqt = Boolean(marker && markerHasDqtTables(marker));
  const label = String(cell.display_name ?? "—");
  const cellTitle =
    typeof cell.reason === "string" ? cell.reason : isDqt ? "Passe o mouse para ver matrizes DQT" : label;

  return (
    <td
      className={[
        "jpeg-compare-grid__marker-cell",
        cell.status === "reference" ? "is-reference" : "",
        cell.status === "match" ? "is-match" : "",
        cell.status === "diverge" || cell.status === "missing" || cell.status === "extra" ? "is-diverge" : "",
        isDqt ? "has-dqt-tooltip" : "",
      ]
        .filter(Boolean)
        .join(" ")}
      style={{ background: bg }}
      onDoubleClick={
        showPlus
          ? (e) => {
              e.stopPropagation();
              onToggleThumb(thumbKey);
            }
          : undefined
      }
    >
      <div className="jpeg-compare-grid__marker-inner">
        {isDqt && marker ? (
          <span
            className="jpeg-compare-dqt-hover"
            title={cellTitle}
            data-testid="dqt-cell"
            onMouseEnter={(e) => dqtHover.onDqtEnter(marker, e.currentTarget)}
            onMouseLeave={dqtHover.onDqtLeave}
          >
            {label}
          </span>
        ) : (
          <span title={cellTitle}>{label}</span>
        )}
        {showPlus && (
          <button
            type="button"
            className={`jpeg-compare-grid__thumb-btn${expanded ? " is-open" : ""}`}
            onClick={(e) => {
              e.stopPropagation();
              onToggleThumb(thumbKey);
            }}
            title="Expandir estrutura do thumbnail"
          >
            +
          </button>
        )}
      </div>
    </td>
  );
}
