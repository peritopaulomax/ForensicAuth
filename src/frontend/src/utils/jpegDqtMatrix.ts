import type { DqtTable, JpegMarkerDump } from "@/utils/jpegStructureCompare";

/** Posições (linha, coluna) na ordem zigzag JPEG (ITU-T T.81). */
const ZIGZAG_RC: ReadonlyArray<readonly [number, number]> = [
  [0, 0], [0, 1], [1, 0], [2, 0], [1, 1], [0, 2], [0, 3], [1, 2],
  [2, 1], [3, 0], [4, 0], [3, 1], [2, 2], [1, 3], [0, 4], [0, 5],
  [1, 4], [2, 3], [3, 2], [4, 1], [5, 0], [6, 0], [5, 1], [4, 2],
  [3, 3], [2, 4], [1, 5], [0, 6], [0, 7], [1, 6], [2, 5], [3, 4],
  [4, 3], [5, 2], [6, 1], [7, 0], [7, 1], [6, 2], [5, 3], [4, 4],
  [3, 5], [2, 6], [1, 7], [2, 7], [3, 6], [4, 5], [5, 4], [6, 3],
  [7, 2], [7, 3], [6, 4], [5, 5], [4, 6], [3, 7], [4, 7], [5, 6],
  [6, 5], [7, 4], [7, 5], [6, 6], [5, 7], [6, 7], [7, 6], [7, 7],
];

function empty8x8(): number[][] {
  return Array.from({ length: 8 }, () => Array(8).fill(0));
}

/** Converte vetor DQT (ordem zigzag) em matriz 8×8 espacial. */
export function dqtFlatToMatrix8x8(flat?: number[] | null): number[][] {
  const matrix = empty8x8();
  if (!flat?.length) return matrix;
  if (Array.isArray(flat[0])) return normalizeDqtMatrix(flat as unknown as number[][]);
  const n = Math.min(64, flat.length);
  for (let i = 0; i < n; i++) {
    const rc = ZIGZAG_RC[i];
    if (!rc) break;
    const [r, c] = rc;
    const val = flat[i];
    matrix[r][c] = typeof val === "number" ? val : Number(val) || 0;
  }
  return matrix;
}

/** Aceita matriz já 8×8 ou vetor zigzag de 64 valores. */
export function normalizeDqtMatrix(raw?: number[] | number[][] | null): number[][] {
  if (!raw?.length) return empty8x8();
  if (Array.isArray(raw[0])) {
    return (raw as number[][]).slice(0, 8).map((row) => {
      const cells = Array.isArray(row) ? row : [];
      return Array.from({ length: 8 }, (_, j) => {
        const val = cells[j];
        return typeof val === "number" ? val : Number(val) || 0;
      });
    });
  }
  return dqtFlatToMatrix8x8(raw as number[]);
}

export function markerHasDqtTables(marker?: JpegMarkerDump | null): boolean {
  return marker?.name === "DQT" && Boolean(marker.dqt_tables?.length);
}

export function dqtTableLabel(table: DqtTable): string {
  const prec = table.precision === 0 ? "8 bit" : "16 bit";
  const role =
    table.table_id === 0 ? "luminância (Y)" : table.table_id === 1 ? "crominância" : `tabela ${table.table_id}`;
  return `Q${table.table_id} — ${role} (${prec})`;
}
