"""Matrix hash sidecar keeps LR cache keys cheap on repeat jobs."""

from __future__ import annotations

import time

from core.reference_data import paths as rd_paths
from core.synthetic_lr_reference import _score_matrix_hash


def test_score_matrix_hash_sidecar_is_fast(tmp_path, monkeypatch):
    rd_paths.clear_path_cache()
    matrix = tmp_path / "reps.csv"
    # Include a path-like column so normalization path is exercised.
    rows = ["path,score\n"] + [f"/tmp/foo/{i},{i}\n" for i in range(5000)]
    matrix.write_text("".join(rows), encoding="utf-8")

    t0 = time.perf_counter()
    h1 = _score_matrix_hash(matrix)
    first = time.perf_counter() - t0
    assert len(h1) == 16
    assert (matrix.with_suffix(matrix.suffix + ".sha16")).is_file()

    t0 = time.perf_counter()
    h2 = _score_matrix_hash(matrix)
    second = time.perf_counter() - t0
    assert h1 == h2
    assert second < 0.05
    assert second < first or first < 0.05
