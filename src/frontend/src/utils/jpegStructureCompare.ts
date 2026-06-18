export type MarkerStatus = "reference" | "match" | "diverge" | "missing" | "extra";

export interface JpegMarkerDump {
  index?: number;
  name: string;
  display_name?: string;
  code_hex?: string;
  offset?: number;
  identifier?: string;
  has_thumbnail?: boolean;
  thumbnail?: JpegThumbnailDump;
  dqt_tables?: DqtTable[];
  dht_tables?: DhtTable[];
}

export interface JpegThumbnailDump {
  available?: boolean;
  markers?: JpegMarkerDump[];
  summary?: string;
}

export interface DqtTable {
  table_id: number;
  precision: number;
  matrix: number[];
}

export interface DhtTable {
  table_class: number;
  table_id: number;
  counts: number[];
  values: number[];
}

export interface JpegStructureDump {
  available?: boolean;
  reason?: string;
  evidence_id?: string;
  label?: string;
  filename?: string;
  comparison_markers?: JpegMarkerDump[];
  markers?: JpegMarkerDump[];
  summary?: string;
}

export interface CompareCell {
  position: number;
  status: MarkerStatus;
  display_name?: string;
  has_thumbnail?: boolean;
  reason?: string | null;
  reference_name?: string | null;
  candidate_name?: string | null;
}

export interface FileComparisonRow {
  is_reference: boolean;
  evidence_id?: string;
  label?: string;
  filename?: string;
  fully_matches: boolean;
  unavailable?: boolean;
  reason?: string;
  cells: CompareCell[];
  /** Padrão de referência inativo (cinza, clicável para ativar). */
  inactive_reference?: boolean;
  /** Agrupa linhas: padrões no topo, questionados embaixo. */
  row_section?: "reference" | "questioned";
}

export interface JpegComparePayload {
  reference_index: number;
  reference_evidence_id?: string;
  reference_label?: string;
  file_count: number;
  max_positions: number;
  all_match: boolean;
  structures: JpegStructureDump[];
  comparisons: FileComparisonRow[];
  errors?: string[];
}

const JPEG_EXT = /\.(jpe?g|jfif)$/i;

export function isJpegEvidenceFilename(name: string): boolean {
  return JPEG_EXT.test(name);
}

export function filterJpegEvidences<T extends { original_filename: string; file_type?: string }>(
  items: T[]
): T[] {
  return items.filter(
    (e) => e.file_type === "imagem" && isJpegEvidenceFilename(e.original_filename)
  );
}

function dqtEqual(a?: DqtTable[], b?: DqtTable[]): boolean {
  if (!a?.length && !b?.length) return true;
  if (!a?.length || !b?.length || a.length !== b.length) return false;
  const norm = (t: DqtTable) => `${t.table_id}:${t.precision}:${t.matrix.join(",")}`;
  const sa = [...a].map(norm).sort();
  const sb = [...b].map(norm).sort();
  return sa.every((v, i) => v === sb[i]);
}

function compareMarkerLists(
  refMarkers: JpegMarkerDump[],
  candMarkers: JpegMarkerDump[]
): { fully_matches: boolean; cells: CompareCell[] } {
  const maxLen = Math.max(refMarkers.length, candMarkers.length);
  const cells: CompareCell[] = [];
  let allMatch = true;

  for (let i = 0; i < maxLen; i++) {
    const refM = refMarkers[i];
    const candM = candMarkers[i];
    const cell = compareSingleMarker(refM, candM, i);
    cells.push(cell);
    if (cell.status !== "match") allMatch = false;
  }

  return { fully_matches: allMatch, cells };
}

function compareSingleMarker(
  refM: JpegMarkerDump | undefined,
  candM: JpegMarkerDump | undefined,
  position: number
): CompareCell {
  const base = (candM || refM || {}) as JpegMarkerDump;
  const display = base.display_name || base.name || "—";
  const hasThumb = Boolean((candM || refM)?.has_thumbnail);

  if (!refM && !candM) {
    return { position, status: "match", display_name: display, has_thumbnail: hasThumb };
  }
  if (!refM) {
    return {
      position,
      status: "extra",
      display_name: display,
      has_thumbnail: hasThumb,
      reason: "marcador extra",
      candidate_name: candM?.name,
    };
  }
  if (!candM) {
    return {
      position,
      status: "missing",
      display_name: display,
      has_thumbnail: hasThumb,
      reason: "marcador ausente",
      reference_name: refM.name,
    };
  }

  if (refM.name !== candM.name) {
    return {
      position,
      status: "diverge",
      display_name: display,
      has_thumbnail: hasThumb,
      reason: `tipo divergente (${candM.name} vs ${refM.name})`,
      reference_name: refM.name,
      candidate_name: candM.name,
    };
  }

  if (refM.name === "DQT" && !dqtEqual(refM.dqt_tables, candM.dqt_tables)) {
    return {
      position,
      status: "diverge",
      display_name: display,
      has_thumbnail: hasThumb,
      reason: "matriz DQT diferente",
      reference_name: refM.name,
      candidate_name: candM.name,
    };
  }

  // DHT: apenas presença/tipo na posição — conteúdo Huffman varia por codificador/conteúdo.

  if (refM.name.startsWith("APP")) {
    const refHas = Boolean(refM.has_thumbnail);
    const candHas = Boolean(candM.has_thumbnail);
    if (refHas && candHas) {
      const thumbMatch = compareMarkerLists(
        refM.thumbnail?.markers || [],
        candM.thumbnail?.markers || []
      ).fully_matches;
      if (!thumbMatch) {
        return {
          position,
          status: "diverge",
          display_name: display,
          has_thumbnail: true,
          reason: "thumbnail APP divergente",
          reference_name: refM.name,
          candidate_name: candM.name,
        };
      }
    } else if (refHas !== candHas) {
      return {
        position,
        status: "diverge",
        display_name: display,
        has_thumbnail: hasThumb,
        reason: "presença de thumbnail divergente",
        reference_name: refM.name,
        candidate_name: candM.name,
      };
    }
  }

  return {
    position,
    status: "match",
    display_name: display,
    has_thumbnail: hasThumb,
    reference_name: refM.name,
    candidate_name: candM.name,
  };
}

export function buildRefVsQuestionedCompare(
  refStructures: JpegStructureDump[],
  questionedStructures: JpegStructureDump[],
  activeRefEvidenceId: string
): JpegComparePayload {
  const activeRef =
    refStructures.find((s) => s.evidence_id === activeRefEvidenceId) || refStructures[0];
  const refMarkers = activeRef?.comparison_markers || [];

  const refRows: FileComparisonRow[] = refStructures.map((struct) => {
    const isActive = struct.evidence_id === activeRef?.evidence_id;
    if (!isActive) {
      return {
        is_reference: true,
        inactive_reference: true,
        row_section: "reference",
        evidence_id: struct.evidence_id,
        label: struct.label,
        filename: struct.filename,
        fully_matches: true,
        cells: [],
      };
    }
    if (!struct.available) {
      return {
        is_reference: true,
        row_section: "reference",
        evidence_id: struct.evidence_id,
        label: struct.label,
        filename: struct.filename,
        fully_matches: false,
        unavailable: true,
        reason: struct.reason,
        cells: [],
      };
    }
    return {
      is_reference: true,
      row_section: "reference",
      evidence_id: struct.evidence_id,
      label: struct.label,
      filename: struct.filename,
      fully_matches: true,
      cells: refMarkers.map((m, i) => ({
        position: i,
        status: "reference" as MarkerStatus,
        display_name: m.display_name || m.name,
        has_thumbnail: Boolean(m.has_thumbnail),
      })),
    };
  });

  const questionedRows: FileComparisonRow[] = questionedStructures.map((struct) => {
    if (!struct.available) {
      return {
        is_reference: false,
        row_section: "questioned",
        evidence_id: struct.evidence_id,
        label: struct.label,
        filename: struct.filename,
        fully_matches: false,
        unavailable: true,
        reason: struct.reason,
        cells: [],
      };
    }
    const cmp = compareMarkerLists(refMarkers, struct.comparison_markers || []);
    return {
      is_reference: false,
      row_section: "questioned",
      evidence_id: struct.evidence_id,
      label: struct.label,
      filename: struct.filename,
      fully_matches: cmp.fully_matches,
      cells: cmp.cells,
    };
  });

  const comparisons = [...refRows, ...questionedRows];
  const structures = [...refStructures, ...questionedStructures];
  const maxPositions = Math.max(...comparisons.map((c) => c.cells.length), 0);

  return {
    reference_index: 0,
    reference_evidence_id: activeRef?.evidence_id,
    reference_label: activeRef?.label,
    file_count: comparisons.length,
    max_positions: maxPositions,
    all_match: questionedRows.filter((c) => !c.unavailable).every((c) => c.fully_matches),
    structures,
    comparisons,
  };
}

export function recomputeComparisons(
  structures: JpegStructureDump[],
  referenceIndex: number
): JpegComparePayload {
  const refIdx = Math.max(0, Math.min(referenceIndex, structures.length - 1));
  const reference = structures[refIdx];
  const refMarkers = reference?.comparison_markers || [];

  const comparisons: FileComparisonRow[] = structures.map((struct, idx) => {
    if (idx === refIdx) {
      return {
        is_reference: true,
        evidence_id: struct.evidence_id,
        label: struct.label,
        filename: struct.filename,
        fully_matches: true,
        cells: refMarkers.map((m, i) => ({
          position: i,
          status: "reference" as MarkerStatus,
          display_name: m.display_name || m.name,
          has_thumbnail: Boolean(m.has_thumbnail),
        })),
      };
    }

    if (!struct.available) {
      return {
        is_reference: false,
        evidence_id: struct.evidence_id,
        label: struct.label,
        filename: struct.filename,
        fully_matches: false,
        unavailable: true,
        reason: struct.reason,
        cells: [],
      };
    }

    const cmp = compareMarkerLists(refMarkers, struct.comparison_markers || []);
    return {
      is_reference: false,
      evidence_id: struct.evidence_id,
      label: struct.label,
      filename: struct.filename,
      fully_matches: cmp.fully_matches,
      cells: cmp.cells,
    };
  });

  const maxPositions = Math.max(...comparisons.map((c) => c.cells.length), 0);

  return {
    reference_index: refIdx,
    reference_evidence_id: reference?.evidence_id,
    reference_label: reference?.label,
    file_count: structures.length,
    max_positions: maxPositions,
    all_match: comparisons
      .filter((c) => !c.is_reference && !c.unavailable)
      .every((c) => c.fully_matches),
    structures,
    comparisons,
  };
}

export function markerAtPosition(
  structures: JpegStructureDump[],
  evidenceId: string | undefined,
  position: number
): JpegMarkerDump | undefined {
  if (!evidenceId) return undefined;
  const struct = structures.find((s) => s.evidence_id === evidenceId);
  return struct?.comparison_markers?.[position];
}

export { normalizeComparePayload as parseComparePayload } from "@/utils/jpegComparePayload";

export const MARKER_CELL_BG: Record<MarkerStatus, string> = {
  reference: "#fef3c7",
  match: "#dcfce7",
  diverge: "#fee2e2",
  missing: "#fee2e2",
  extra: "#fee2e2",
};

export const ROW_BG: Record<"reference" | "match" | "diverge" | "unavailable" | "inactive_ref", string> = {
  reference: "#fffbeb",
  match: "#f0fdf4",
  diverge: "#fef2f2",
  unavailable: "#f9fafb",
  inactive_ref: "#f3f4f6",
};
