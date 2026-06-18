import type { JpegComparePayload } from "@/utils/jpegStructureCompare";
import type { JpegStructureMatrixPayload } from "@/utils/jpegStructureMatrix";

export interface MatrixLegendEntry {
  alias: string;
  label: string;
  role: "reference" | "questioned";
  evidence_id?: string;
}

export interface MatrixDisplayLabels {
  rowAliases: string[];
  colAliases: string[];
  legend: MatrixLegendEntry[];
}

function aliasFor(role: "reference" | "questioned", index: number): string {
  const prefix = role === "reference" ? "R" : "Q";
  return `${prefix}${index + 1}`;
}

export function buildMatrixDisplayLabels(data: JpegStructureMatrixPayload): MatrixDisplayLabels {
  const matrix = data.matrix;
  if (!matrix) {
    return { rowAliases: [], colAliases: [], legend: [] };
  }

  const legend: MatrixLegendEntry[] = [];
  const rowAliases: string[] = [];
  const colAliases: string[] = [];

  if (data.mode === "with_reference") {
    matrix.row_labels.forEach((label, i) => {
      const row = matrix.rows[i];
      const alias = aliasFor("reference", i);
      rowAliases.push(alias);
      legend.push({
        alias,
        label,
        role: "reference",
        evidence_id: row?.evidence_id,
      });
    });
    matrix.col_labels.forEach((label, i) => {
      const alias = aliasFor("questioned", i);
      colAliases.push(alias);
      const cell = matrix.rows[0]?.cells[i];
      legend.push({
        alias,
        label,
        role: "questioned",
        evidence_id: cell?.questioned_evidence_id,
      });
    });
  } else {
    matrix.row_labels.forEach((label, i) => {
      const alias = aliasFor("questioned", i);
      rowAliases.push(alias);
      const row = matrix.rows[i];
      if (!legend.some((e) => e.alias === alias)) {
        legend.push({
          alias,
          label,
          role: "questioned",
          evidence_id: row?.evidence_id,
        });
      }
    });
    matrix.col_labels.forEach((_label, i) => {
      colAliases.push(aliasFor("questioned", i));
    });
  }

  return { rowAliases, colAliases, legend };
}

/** Aliases por linha da grade posicional (R* / Q*), alinhados à legenda da matriz. */
export function buildCompareGridRowAliases(data: JpegComparePayload): string[] {
  const hasRefSection = data.comparisons.some((r) => r.row_section === "reference");
  const aliases: string[] = [];
  let refIdx = 0;
  let questIdx = 0;

  for (const row of data.comparisons) {
    if (hasRefSection && row.row_section === "reference") {
      aliases.push(aliasFor("reference", refIdx++));
    } else if (hasRefSection && row.row_section === "questioned") {
      aliases.push(aliasFor("questioned", questIdx++));
    } else {
      aliases.push(aliasFor("questioned", questIdx++));
    }
  }

  return aliases;
}
