"""Discrete wavelet transform — faithful port of Peritus waveletnoiseresidue/dwt.c."""

from __future__ import annotations

import numpy as np


def _mat(arr: np.ndarray, row: int, col: int) -> float:
    return float(arr[row, col])


def _set_mat(arr: np.ndarray, row: int, col: int, value: float) -> None:
    arr[row, col] = value


def dwt_coefficients(h: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    ncoeff = h.shape[0]
    coeff_low = np.empty(ncoeff, dtype=np.float64)
    coeff_high = np.empty(ncoeff, dtype=np.float64)
    for i in range(ncoeff):
        coeff_low[i] = h[(ncoeff - i) - 1]
        coeff_high[i] = h[i]
    for i in range(0, ncoeff, 2):
        coeff_high[i] = -coeff_high[i]
    return coeff_low, coeff_high


def dwt_convolution(
    x_in: np.ndarray,
    lx: int,
    coeff_low: np.ndarray,
    coeff_high: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    ncoeff_minus_one = coeff_low.shape[0] - 1
    buf = np.empty(lx + ncoeff_minus_one, dtype=np.float64)
    buf[:lx] = x_in[:lx]
    for i in range(lx, lx + ncoeff_minus_one):
        buf[i] = buf[i - lx]

    x_out_low = np.empty((lx + 1) // 2 if lx else 0, dtype=np.float64)
    x_out_high = np.empty((lx + 1) // 2 if lx else 0, dtype=np.float64)
    ind = 0
    for i in range(0, lx, 2):
        x0 = 0.0
        x1 = 0.0
        for j in range(ncoeff_minus_one + 1):
            x0 += buf[i + j] * coeff_low[ncoeff_minus_one - j]
            x1 += buf[i + j] * coeff_high[ncoeff_minus_one - j]
        x_out_low[ind] = x0
        x_out_high[ind] = x1
        ind += 1
    return x_out_low, x_out_high


def dwt_x(x: np.ndarray, h: np.ndarray, levels: int) -> np.ndarray:
    """
    2D DWT matching Peritus dwtX (Rice-style layout in output matrix).

    x: 2D float64 image (rows, cols)
    h: scaling coefficients (Daubechies order 2/4/6/8/10)
    levels: decomposition levels (Peritus uses 1)
    """
    nrows, ncols = x.shape
    y = np.zeros((nrows, ncols), dtype=np.float64)
    coeff_low, coeff_high = dwt_coefficients(h)
    ncoeff_minus_one = h.shape[0] - 1

    work_rows = nrows
    work_cols = ncols
    if work_cols == 1:
        work_cols = work_rows
        work_rows = 1

    current_rows = 2 * work_rows
    current_cols = 2 * work_cols

    for current_level in range(1, levels + 1):
        if work_rows == 1:
            current_rows = 1
            row_cursor = 0
        else:
            current_rows = current_rows // 2
            row_cursor = current_rows // 2
        current_cols = current_cols // 2
        column_cursor = current_cols // 2

        x_dummy = np.empty(current_cols + ncoeff_minus_one, dtype=np.float64)
        y_dummy_low = np.empty(current_cols, dtype=np.float64)
        y_dummy_high = np.empty(current_cols, dtype=np.float64)

        for idx_rows in range(current_rows):
            if current_level == 1:
                for i in range(current_cols):
                    x_dummy[i] = _mat(x, idx_rows, i)
            else:
                for i in range(current_cols):
                    x_dummy[i] = _mat(y, idx_rows, i)

            y_dummy_low, y_dummy_high = dwt_convolution(
                x_dummy, current_cols, coeff_low, coeff_high
            )
            idx_columns = column_cursor
            for i in range(column_cursor):
                _set_mat(y, idx_rows, i, y_dummy_low[i])
                _set_mat(y, idx_rows, idx_columns, y_dummy_high[i])
                idx_columns += 1

        if work_rows > 1:
            x_dummy = np.empty(current_rows + ncoeff_minus_one, dtype=np.float64)
            y_dummy_low = np.empty(current_rows, dtype=np.float64)
            y_dummy_high = np.empty(current_rows, dtype=np.float64)
            for idx_columns in range(current_cols):
                for i in range(current_rows):
                    x_dummy[i] = _mat(y, i, idx_columns)
                y_dummy_low, y_dummy_high = dwt_convolution(
                    x_dummy, current_rows, coeff_low, coeff_high
                )
                idx_rows = row_cursor
                for i in range(row_cursor):
                    _set_mat(y, i, idx_columns, y_dummy_low[i])
                    _set_mat(y, idx_rows, idx_columns, y_dummy_high[i])
                    idx_rows += 1

    return y


def scaling_coefficients(order: int) -> np.ndarray:
    """Daubechies scaling coefficients (Peritus filter.cpp switch)."""
    tables: dict[int, list[float]] = {
        2: [0.707106781186547, 0.707106781186547],
        4: [0.482962912597969, 0.836516303770614, 0.224143869747321, -0.129409521425324],
        6: [
            0.332670553432331,
            0.806891509628051,
            0.459877500247080,
            -0.135011022703753,
            -0.085441274798198,
            0.035226291956915,
        ],
        8: [
            0.230377813309,
            0.714846570553,
            0.630880767930,
            -0.027983769417,
            -0.187034811719,
            0.030841381836,
            0.032883011667,
            -0.010597401785,
        ],
        10: [
            0.160102396980101,
            0.603829271025217,
            0.724308529193500,
            0.138428145668299,
            -0.242294884520350,
            -0.032244868420488,
            0.077571488132616,
            -0.006241490168642,
            -0.012580751992427,
            0.003335725296412,
        ],
    }
    if order not in tables:
        raise ValueError(f"order deve ser 2, 4, 6, 8 ou 10 (recebido {order})")
    return np.array(tables[order], dtype=np.float64)
