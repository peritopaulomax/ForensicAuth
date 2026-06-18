"""Subprocess worker: one (image, n_jobs) Copy-Move PCA timing (fresh Numba pool)."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

# Must be set before copy_move_pca (and thus numba) is imported.
if len(sys.argv) < 4:
    raise SystemExit("usage: worker.py <gray.npy> <n_jobs> <repeats>")

npy_path = Path(sys.argv[1])
n_jobs = int(sys.argv[2])
repeats = max(1, int(sys.argv[3]))

os.environ["COPY_MOVE_PCA_N_JOBS"] = str(n_jobs)

backend = Path(__file__).resolve().parents[1] / "src" / "backend"
sys.path.insert(0, str(backend))

import numpy as np  # noqa: E402

from core.legacy.copy_move_pca import run_copy_move_pca  # noqa: E402

gray = np.load(npy_path)
params = {"max_side": 0, "mem_budget_bytes": 0, "morph": True, "nf": 128, "nd": 16}

# Warm-up (JIT + thread pools)
run_copy_move_pca(gray, params)

samples: list[float] = []
for _ in range(repeats):
    t0 = time.perf_counter()
    out = run_copy_move_pca(gray, params)
    samples.append(time.perf_counter() - t0)

payload = {
    "n_jobs": n_jobs,
    "seconds": samples,
    "best_seconds": min(samples),
    "median_seconds": float(np.median(samples)),
    "parallel_threads": out.get("parallel_threads"),
    "nb_blocks": out.get("nb_blocks"),
}
print(json.dumps(payload))
