/** Tabela de luminância padrão JPEG (ITU-T T.81 Annex K / libjpeg) e escala por qualidade. */

/** Matriz base de luminância (qualidade nominal 50 na escala libjpeg). */
export const LIBJPEG_LUMA_BASE: ReadonlyArray<ReadonlyArray<number>> = [
  [16, 11, 10, 16, 24, 40, 51, 61],
  [12, 12, 14, 19, 26, 58, 60, 55],
  [14, 13, 16, 24, 40, 57, 69, 56],
  [14, 17, 22, 29, 51, 87, 80, 62],
  [18, 22, 37, 56, 68, 109, 103, 77],
  [24, 35, 55, 64, 81, 104, 113, 92],
  [49, 64, 78, 87, 103, 121, 120, 101],
  [72, 92, 95, 98, 112, 100, 103, 99],
];

export const DEFAULT_LIBJPEG_QUALITY = 80;

/** Qualidade JPEG válida para escala libjpeg (1–100). */
export function clampJpegQuality(quality: number): number {
  if (!Number.isFinite(quality)) return DEFAULT_LIBJPEG_QUALITY;
  return Math.max(1, Math.min(100, Math.round(quality)));
}

/**
 * Fator de escala libjpeg (`jcparam.c` / `jpeg_set_quality`).
 * quality &lt; 50 → 5000/q ; senão → 200 − 2q.
 */
export function libjpegQualityScale(quality: number): number {
  const q = clampJpegQuality(quality);
  if (q < 50) {
    return Math.floor(5000 / q);
  }
  return 200 - q * 2;
}

/** Matriz 8×8 de luminância libjpeg para a qualidade informada. */
export function libjpegLumaQuantizationMatrix(quality: number = DEFAULT_LIBJPEG_QUALITY): number[][] {
  const scale = libjpegQualityScale(quality);
  return LIBJPEG_LUMA_BASE.map((row) =>
    row.map((base) => {
      const temp = Math.floor((base * scale + 50) / 100);
      return Math.max(1, Math.min(255, temp));
    })
  );
}

export function cloneMatrix8x8(matrix: number[][]): number[][] {
  return matrix.map((row) => [...row]);
}
