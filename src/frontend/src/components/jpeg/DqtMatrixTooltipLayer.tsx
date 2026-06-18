import { createPortal } from "react-dom";
import DqtMatrixGrid from "@/components/jpeg/DqtMatrixGrid";
import type { JpegMarkerDump } from "@/utils/jpegStructureCompare";
import { dqtTableLabel, markerHasDqtTables, normalizeDqtMatrix } from "@/utils/jpegDqtMatrix";

export interface DqtTooltipState {
  marker: JpegMarkerDump;
  top: number;
  left: number;
}

export default function DqtMatrixTooltipLayer({
  state,
  onMouseEnter,
  onMouseLeave,
}: {
  state: DqtTooltipState | null;
  onMouseEnter: () => void;
  onMouseLeave: () => void;
}) {
  if (!state || !markerHasDqtTables(state.marker)) return null;

  const tables = (state.marker.dqt_tables || []).filter(
    (t) => Array.isArray(t.matrix) && t.matrix.length > 0
  );
  if (tables.length === 0) return null;

  return createPortal(
    <div
      className="jpeg-dqt-tooltip jpeg-dqt-tooltip--portal"
      role="tooltip"
      style={{ top: state.top, left: state.left }}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      data-testid="dqt-tooltip"
    >
      <span className="jpeg-dqt-tooltip__title">Matrizes de quantização (DQT)</span>
      <div className="jpeg-dqt-tooltip__body">
        {tables.map((table, idx) => (
          <DqtMatrixGrid
            key={`dqt-${table.table_id}-${idx}`}
            matrix={normalizeDqtMatrix(table.matrix)}
            title={dqtTableLabel(table)}
          />
        ))}
      </div>
    </div>,
    document.body
  );
}
