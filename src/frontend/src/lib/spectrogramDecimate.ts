/** Max-pool decimation (port of spectrogram_decimate.py) for client-side display. */

export const DEFAULT_MAX_TIME_BINS = 2000;
export const DEFAULT_MAX_FREQ_BINS = 512;

export interface SpectrogramDecimationMeta {
  decimated: boolean;
  full_shape: [number, number];
  display_shape: [number, number];
  row_pool_factor: number;
  col_pool_factor: number;
}

function min2d(rows: number[][]): number {
  let m = Infinity;
  for (const row of rows) {
    for (const v of row) {
      if (v < m) m = v;
    }
  }
  return Number.isFinite(m) ? m : -120;
}

export function decimateSpectrogramMaxPool(
  magnitudeDb: number[][],
  times: number[],
  frequencies: number[],
  maxTimeBins = DEFAULT_MAX_TIME_BINS,
  maxFreqBins = DEFAULT_MAX_FREQ_BINS
): {
  magnitude_db: number[][];
  times: number[];
  frequencies: number[];
  meta: SpectrogramDecimationMeta;
} {
  const nRows = magnitudeDb.length;
  const nCols = nRows > 0 ? magnitudeDb[0].length : 0;
  const meta: SpectrogramDecimationMeta = {
    decimated: false,
    full_shape: [nRows, nCols],
    display_shape: [nRows, nCols],
    row_pool_factor: 1,
    col_pool_factor: 1,
  };

  if (nCols <= maxTimeBins && nRows <= maxFreqBins) {
    return { magnitude_db: magnitudeDb, times, frequencies, meta };
  }

  const colFactor = Math.max(1, Math.ceil(nCols / maxTimeBins));
  const rowFactor = Math.max(1, Math.ceil(nRows / maxFreqBins));
  const nColsOut = Math.ceil(nCols / colFactor);
  const nRowsOut = Math.ceil(nRows / rowFactor);
  const padValue = min2d(magnitudeDb);

  const zOut: number[][] = [];
  for (let ri = 0; ri < nRowsOut; ri++) {
    const row: number[] = [];
    for (let ci = 0; ci < nColsOut; ci++) {
      let peak = padValue;
      for (let dr = 0; dr < rowFactor; dr++) {
        const r = ri * rowFactor + dr;
        if (r >= nRows) continue;
        for (let dc = 0; dc < colFactor; dc++) {
          const c = ci * colFactor + dc;
          if (c >= nCols) continue;
          peak = Math.max(peak, magnitudeDb[r][c]);
        }
      }
      row.push(peak);
    }
    zOut.push(row);
  }

  const timesOut: number[] = [];
  for (let ci = 0; ci < nColsOut; ci++) {
    const idx = Math.min(ci * colFactor + Math.floor(colFactor / 2), nCols - 1);
    timesOut.push(times[idx]);
  }

  const freqsOut: number[] = [];
  for (let ri = 0; ri < nRowsOut; ri++) {
    const idx = Math.min(ri * rowFactor + Math.floor(rowFactor / 2), nRows - 1);
    freqsOut.push(frequencies[idx]);
  }

  meta.decimated = true;
  meta.display_shape = [nRowsOut, nColsOut];
  meta.row_pool_factor = rowFactor;
  meta.col_pool_factor = colFactor;

  return { magnitude_db: zOut, times: timesOut, frequencies: freqsOut, meta };
}

export function applySpectrogramDisplayOptions(
  full: {
    times: number[];
    frequencies: number[];
    magnitude_db: number[][];
  },
  decimate: boolean
) {
  if (!decimate) {
    const nRows = full.magnitude_db.length;
    const nCols = nRows > 0 ? full.magnitude_db[0].length : 0;
    return {
      ...full,
      meta: {
        decimated: false,
        full_shape: [nRows, nCols] as [number, number],
        display_shape: [nRows, nCols] as [number, number],
        row_pool_factor: 1,
        col_pool_factor: 1,
      },
    };
  }
  const out = decimateSpectrogramMaxPool(full.magnitude_db, full.times, full.frequencies);
  return { ...out, meta: out.meta };
}
