#!/usr/bin/env python3
"""Benchmark Copy-Move PCA vs COPY_MOVE_PCA_N_JOBS (subprocess per job count)."""

from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[1]
OUT_DIR = WORKSPACE / "results" / "benchmarks"
OUT_DIR.mkdir(parents=True, exist_ok=True)

JOB_COUNTS = [1, 2, 4, 8, 12, 16, 20, 24, 32, 40, 48]
SCENARIOS = [
    ("small_300x400", 400, 300),
    ("large_3000x2000", 2000, 3000),
]
WARMUP = 1
REPEATS = 3
LARGE_REPEATS = 1
LARGE_WARMUP = 0

WORKER = r'''
import os
import sys
import time
import numpy as np

n_jobs = int(sys.argv[1])
w, h = int(sys.argv[2]), int(sys.argv[3])
warmup = int(sys.argv[4])
repeats = int(sys.argv[5])
os.environ["COPY_MOVE_PCA_N_JOBS"] = str(n_jobs)
os.environ["NUMBA_NUM_THREADS"] = str(n_jobs)
os.environ["OPENBLAS_NUM_THREADS"] = str(n_jobs)
os.environ["OMP_NUM_THREADS"] = str(n_jobs)
os.environ["MKL_NUM_THREADS"] = str(n_jobs)

sys.path.insert(0, os.environ["PYTHONPATH"])

rng = np.random.default_rng(42)
gray = rng.integers(40, 200, (h, w), dtype=np.uint8)
ph, pw = min(h // 4, 80), min(w // 4, 80)
if ph > 8 and pw > 8:
    patch = gray[10 : 10 + ph, 10 : 10 + pw].copy()
    gray[h - ph - 10 : h - 10, w - pw - 10 : w - 10] = patch

from core.legacy.copy_move_pca.parallel_config import configure_copy_move_parallelism
from core.legacy.copy_move_pca.reference_cpp import run_copy_move_pca_reference

configure_copy_move_parallelism(n_jobs)

for _ in range(warmup):
    run_copy_move_pca_reference(gray, nf=128, morph=False)

times = []
for _ in range(repeats):
    t0 = time.perf_counter()
    run_copy_move_pca_reference(gray, nf=128, morph=False)
    times.append(time.perf_counter() - t0)

print(min(times))
'''


def _run_one(n_jobs: int, width: int, height: int, *, warmup: int, repeats: int) -> float:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(WORKSPACE / "src" / "backend")
    cmd = [
        sys.executable,
        "-c",
        WORKER,
        str(n_jobs),
        str(width),
        str(height),
        str(warmup),
        str(repeats),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=str(WORKSPACE))
    if proc.returncode != 0:
        raise RuntimeError(f"n_jobs={n_jobs} {width}x{height} failed:\n{proc.stderr}")
    return float(proc.stdout.strip().splitlines()[-1])


def main() -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    rows: list[dict] = []

    for scenario, width, height in SCENARIOS:
        is_large = width * height > 1_000_000
        warmup = LARGE_WARMUP if is_large else WARMUP
        repeats = LARGE_REPEATS if is_large else REPEATS
        print(f"=== {scenario} ({width}x{height}) warmup={warmup} repeats={repeats} ===", flush=True)
        for n_jobs in JOB_COUNTS:
            try:
                elapsed = _run_one(n_jobs, width, height, warmup=warmup, repeats=repeats)
                row = {
                    "scenario": scenario,
                    "width": width,
                    "height": height,
                    "n_jobs": n_jobs,
                    "seconds_min": round(elapsed, 4),
                }
                rows.append(row)
                print(f"  n_jobs={n_jobs:2d} -> {elapsed:.3f}s", flush=True)
            except Exception as exc:
                print(f"  n_jobs={n_jobs:2d} FAILED: {exc}", flush=True)
                rows.append(
                    {
                        "scenario": scenario,
                        "width": width,
                        "height": height,
                        "n_jobs": n_jobs,
                        "seconds_min": None,
                        "error": str(exc),
                    }
                )

    csv_path = OUT_DIR / f"copy_move_pca_jobs_{stamp}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["scenario", "width", "height", "n_jobs", "seconds_min"])
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k) for k in writer.fieldnames})

    meta = {
        "timestamp": stamp,
        "job_counts": JOB_COUNTS,
        "scenarios": [{"name": s, "width": w, "height": h} for s, w, h in SCENARIOS],
        "warmup": WARMUP,
        "repeats": REPEATS,
        "csv": str(csv_path),
    }

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(1, 2, figsize=(12, 5), sharey=False)
        for ax, (scenario, _w, _h) in zip(axes, SCENARIOS):
            subset = [r for r in rows if r["scenario"] == scenario and r.get("seconds_min") is not None]
            xs = [r["n_jobs"] for r in subset]
            ys = [r["seconds_min"] for r in subset]
            ax.plot(xs, ys, "o-", linewidth=2, markersize=6)
            ax.set_title(scenario)
            ax.set_xlabel("COPY_MOVE_PCA_N_JOBS")
            ax.set_ylabel("Tempo (s, min de 3 repetições)")
            ax.grid(True, alpha=0.3)
            if ys:
                best_i = min(range(len(ys)), key=lambda i: ys[i])
                ax.axvline(xs[best_i], color="green", linestyle="--", alpha=0.5, label=f"ótimo={xs[best_i]}")
                ax.legend()
        fig.suptitle("Copy-Move PCA — tempo vs paralelismo")
        fig.tight_layout()
        png_path = OUT_DIR / f"copy_move_pca_jobs_{stamp}.png"
        fig.savefig(png_path, dpi=150)
        plt.close(fig)
        meta["png"] = str(png_path)
        print(f"Gráfico: {png_path}", flush=True)
    except ImportError:
        print("matplotlib ausente — CSV salvo sem gráfico", flush=True)

    json_path = OUT_DIR / f"copy_move_pca_jobs_{stamp}.json"
    json_path.write_text(json.dumps({"meta": meta, "rows": rows}, indent=2), encoding="utf-8")
    print(f"CSV: {csv_path}", flush=True)
    print(f"JSON: {json_path}", flush=True)


if __name__ == "__main__":
    main()
