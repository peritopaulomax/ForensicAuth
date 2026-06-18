import type {
  CompareCell,
  FileComparisonRow,
  JpegComparePayload,
  JpegMarkerDump,
  JpegStructureDump,
} from "@/utils/jpegStructureCompare";

const MAX_GRID_COLUMNS = 128;

function asString(value: unknown, fallback = "—"): string {
  return typeof value === "string" && value.length > 0 ? value : fallback;
}

function slimMarker(marker: unknown): JpegMarkerDump | undefined {
  if (!marker || typeof marker !== "object") return undefined;
  const m = marker as Record<string, unknown>;
  const name = asString(m.name, "");
  if (!name) return undefined;

  const out: JpegMarkerDump = {
    name,
    display_name: typeof m.display_name === "string" ? m.display_name : name,
    has_thumbnail: Boolean(m.has_thumbnail),
  };

  if (name === "DQT" && Array.isArray(m.dqt_tables)) {
    out.dqt_tables = m.dqt_tables
      .filter((t) => t && typeof t === "object")
      .map((t) => {
        const row = t as Record<string, unknown>;
        return {
          table_id: Number(row.table_id) || 0,
          precision: Number(row.precision) || 0,
          matrix: Array.isArray(row.matrix) ? row.matrix.map((v) => Number(v) || 0) : [],
        };
      });
  }

  const thumb = m.thumbnail;
  if (out.has_thumbnail && thumb && typeof thumb === "object") {
    const t = thumb as Record<string, unknown>;
    const markers = Array.isArray(t.markers)
      ? t.markers.map(slimMarker).filter((x): x is JpegMarkerDump => Boolean(x))
      : [];
    out.thumbnail = {
      summary: typeof t.summary === "string" ? t.summary : undefined,
      markers,
    };
  }

  return out;
}

function slimStructure(raw: unknown): JpegStructureDump {
  if (!raw || typeof raw !== "object") return { available: false };
  const s = raw as Record<string, unknown>;
  const markers = Array.isArray(s.comparison_markers)
    ? s.comparison_markers.map(slimMarker).filter((x): x is JpegMarkerDump => Boolean(x))
    : [];

  return {
    available: Boolean(s.available),
    reason: typeof s.reason === "string" ? s.reason : undefined,
    evidence_id: typeof s.evidence_id === "string" ? s.evidence_id : undefined,
    label: typeof s.label === "string" ? s.label : undefined,
    filename: typeof s.filename === "string" ? s.filename : undefined,
    comparison_markers: markers,
    summary: typeof s.summary === "string" ? s.summary : undefined,
  };
}

function slimCell(raw: unknown, index: number): CompareCell {
  if (!raw || typeof raw !== "object") {
    return { position: index, status: "missing", display_name: "—" };
  }
  const c = raw as Record<string, unknown>;
  const status = c.status;
  const validStatus =
    status === "reference" ||
    status === "match" ||
    status === "diverge" ||
    status === "missing" ||
    status === "extra"
      ? status
      : "diverge";

  return {
    position: Number(c.position ?? index),
    status: validStatus,
    display_name: asString(c.display_name),
    has_thumbnail: Boolean(c.has_thumbnail),
    reason: typeof c.reason === "string" ? c.reason : null,
    reference_name: typeof c.reference_name === "string" ? c.reference_name : null,
    candidate_name: typeof c.candidate_name === "string" ? c.candidate_name : null,
  };
}

function slimComparisonRow(raw: unknown): FileComparisonRow {
  if (!raw || typeof raw !== "object") {
    return { is_reference: false, fully_matches: false, cells: [] };
  }
  const r = raw as Record<string, unknown>;
  const cells = Array.isArray(r.cells) ? r.cells.map(slimCell) : [];
  return {
    is_reference: Boolean(r.is_reference),
    evidence_id: typeof r.evidence_id === "string" ? r.evidence_id : undefined,
    label: typeof r.label === "string" ? r.label : undefined,
    filename: typeof r.filename === "string" ? r.filename : undefined,
    fully_matches: Boolean(r.fully_matches),
    unavailable: Boolean(r.unavailable),
    reason: typeof r.reason === "string" ? r.reason : undefined,
    cells,
  };
}

export function slimStructuresList(raw: unknown): JpegStructureDump[] {
  if (!Array.isArray(raw)) return [];
  return raw.map(slimStructure);
}

export function normalizeComparePayload(result: Record<string, unknown>): JpegComparePayload | null {
  if (result.success === false) return null;

  const structuresRaw = result.structures;
  const comparisonsRaw = result.comparisons;
  if (!Array.isArray(structuresRaw) || !Array.isArray(comparisonsRaw)) return null;

  const structures = structuresRaw.map(slimStructure);
  const comparisons = comparisonsRaw.map(slimComparisonRow);

  const maxFromRows = comparisons.reduce((max, row) => Math.max(max, row.cells.length), 0);
  const maxPositions = Math.min(
    MAX_GRID_COLUMNS,
    Math.max(0, Number(result.max_positions ?? maxFromRows) || maxFromRows)
  );

  return {
    reference_index: Math.max(0, Number(result.reference_index ?? 0)),
    reference_evidence_id:
      typeof result.reference_evidence_id === "string" ? result.reference_evidence_id : undefined,
    reference_label: typeof result.reference_label === "string" ? result.reference_label : undefined,
    file_count: Number(result.file_count ?? structures.length) || structures.length,
    max_positions: maxPositions,
    all_match: Boolean(result.all_match),
    structures,
    comparisons,
    errors: Array.isArray(result.errors) ? result.errors.map((e) => String(e)) : [],
  };
}
