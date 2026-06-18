export interface JpegMatrixCell {
  col_index: number;
  matches: boolean;
  unavailable?: boolean;
  reason?: string | null;
  questioned_evidence_id?: string;
  questioned_label?: string;
}

export interface JpegMatrixRow {
  row_index: number;
  evidence_id?: string;
  label: string;
  cells: JpegMatrixCell[];
}

import type { JpegStructureDump } from "@/utils/jpegStructureCompare";

export interface JpegStructureMatrixPayload {
  mode: "with_reference" | "all_pairs";
  reference_count: number;
  questioned_count: number;
  matrix?: {
    row_labels: string[];
    col_labels: string[];
    rows: JpegMatrixRow[];
  };
  reference_structures?: JpegStructureDump[];
  questioned_structures?: JpegStructureDump[];
  errors?: string[];
}

export function parseJpegStructureMatrix(result: Record<string, unknown>): JpegStructureMatrixPayload | null {
  const mode = result.mode;
  if (mode !== "with_reference" && mode !== "all_pairs") return null;
  const matrix = result.matrix;
  if (!matrix || typeof matrix !== "object") return null;
  const m = matrix as Record<string, unknown>;
  if (!Array.isArray(m.rows) || !Array.isArray(m.col_labels)) return null;
  const structures = (raw: unknown): JpegStructureDump[] =>
    Array.isArray(raw) ? (raw as JpegStructureDump[]) : [];

  return {
    mode,
    reference_count: Number(result.reference_count ?? 0),
    questioned_count: Number(result.questioned_count ?? 0),
    matrix: {
      row_labels: Array.isArray(m.row_labels) ? m.row_labels.map(String) : [],
      col_labels: m.col_labels.map(String),
      rows: m.rows as JpegMatrixRow[],
    },
    reference_structures: structures(result.reference_structures),
    questioned_structures: structures(result.questioned_structures),
    errors: Array.isArray(result.errors) ? result.errors.map(String) : [],
  };
}
