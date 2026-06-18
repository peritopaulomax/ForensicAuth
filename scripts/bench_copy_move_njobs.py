#!/usr/bin/env python3
"""Benchmark Copy-Move PCA vs COPY_MOVE_PCA_N_JOBS and plot optimal thread count."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

WORKSPACE = Path(__file__).resolve().parents[1]
WORKER = WORKSPACE / "scripts" / "bench_copy_move_njobs_worker.py"
OUT_DIR = WORKSPACE / "results" / "benchmarks"

SCENARIOS = {
    "585x343 (pequena)": (343, 585),
    "3872x2592 (grande)": (2592, 3872),
}

DEFAULT_NJOBS = [1, 2, 4, 8, 12, 16, 24, 32, 48]


def _synthetic_random(h: int, w: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.integers(30, 220, (h, w), dtype=np.uint8)


def _run_worker(python: str, npy: Path, n_jobs: int, repeats: int) -> dict:
    proc = subprocess.run(
        [python, str(WORKER), str(npy), str(n_jobs), str(repeats)],
        capture_output=True,
        text=True,
        cwd=str(WORKSPACE),
        env={**os.environ, "PYTHONPATH": str(WORKSPACE / "src" / "backend")},
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"n_jobs={n_jobs} failed (code {proc.returncode})\n"
            f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    line = proc.stdout.strip().splitlines()[-1]
    return json.loads(line)


def _annotate_optimum(ax, xs, ys, label_prefix: str) -> None:
    best_i = int(np.argmin(ys))
    best_x, best_y = xs[best_i], ys[best_i]
    ax.scatter([best_x], [best_y], color="crimson", s=120, zorder=5, marker="*")
    ax.annotate(
        f"{label_prefix} ótimo: {best_x} threads\n{best_y:.2f}s",
        xy=(best_x, best_y),
        xytext=(12, 14),
        textcoords="offset points",
        fontsize=9,
        bbox={"boxstyle": "round,pad=0.35", "fc": "#fff3cd", "ec": "#856404"},
        arrowprops={"arrowstyle": "->", "color": "crimson"},
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--n-jobs",
        type=int,
        nargs="+",
        default=DEFAULT_NJOBS,
        help="Thread counts to benchmark (default: 1 2 4 8 12 16 24 32 48)",
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=2,
        help="Timed repetitions per config after warm-up (default: 2)",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Only small image + fewer n_jobs (1 4 8 16 48)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="PNG output path (default: results/benchmarks/copy_move_pca_njobs_<ts>.png)",
    )
    args = parser.parse_args()

    n_jobs_list = sorted(set(args.n_jobs))
    scenarios = dict(SCENARIOS)
    if args.quick:
        scenarios = {"585x343 (pequena)": SCENARIOS["585x343 (pequena)"]}
        n_jobs_list = [n for n in [1, 4, 8, 16, 48] if n in n_jobs_list or not args.n_jobs]

    python = sys.executable
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_png = args.output or (OUT_DIR / f"copy_move_pca_njobs_{stamp}.png")
    out_json = out_png.with_suffix(".json")

    results: dict[str, list[dict]] = {}
    cache_dir = OUT_DIR / f"fixtures_{stamp}"
    cache_dir.mkdir(parents=True, exist_ok=True)

    print(f"Python: {python}")
    print(f"CPU cores (logical): {os.cpu_count()}")
    print(f"n_jobs sweep: {n_jobs_list}")
    print(f"Scenarios: {list(scenarios.keys())}")
    print("-" * 60)

    for label, (h, w) in scenarios.items():
        npy = cache_dir / f"gray_{h}x{w}.npy"
        gray = _synthetic_random(h, w, seed=42 if h < 1000 else 7)
        np.save(npy, gray)
        print(f"\n[{label}] {w}x{h} px — {gray.nbytes / 1e6:.1f} MB")
        rows: list[dict] = []

        for n_jobs in n_jobs_list:
            t0 = time.perf_counter()
            row = _run_worker(python, npy, n_jobs, args.repeats)
            wall = time.perf_counter() - t0
            row["label"] = label
            row["width"] = w
            row["height"] = h
            row["wall_seconds"] = wall
            rows.append(row)
            print(
                f"  n_jobs={n_jobs:2d}  best={row['best_seconds']:.3f}s  "
                f"median={row['median_seconds']:.3f}s  (subprocess {wall:.1f}s)"
            )

        results[label] = rows

    # Plot
    n_panels = len(scenarios)
    fig, axes = plt.subplots(1, n_panels, figsize=(6.5 * n_panels, 5), squeeze=False)

    for ax, (label, rows) in zip(axes[0], results.items()):
        xs = [r["n_jobs"] for r in rows]
        ys_best = [r["best_seconds"] for r in rows]
        ys_med = [r["median_seconds"] for r in rows]

        ax.plot(xs, ys_med, "o-", color="#2563eb", linewidth=2, markersize=7, label="Mediana")
        ax.plot(xs, ys_best, "s--", color="#16a34a", linewidth=1.5, markersize=6, label="Melhor")
        _annotate_optimum(ax, xs, ys_best, label.split()[0])
        ax.set_title(label, fontsize=12, fontweight="bold")
        ax.set_xlabel("COPY_MOVE_PCA_N_JOBS")
        ax.set_ylabel("Tempo (s)")
        ax.set_xticks(xs)
        ax.grid(True, alpha=0.35)
        ax.legend(loc="upper right", fontsize=9)

    fig.suptitle(
        "Copy-Move PCA — tempo vs paralelismo\n"
        f"(imagens aleatórias sintéticas, morph=True, nf=128; {args.repeats} repetições pós warm-up)",
        fontsize=13,
        fontweight="bold",
        y=1.02,
    )
    fig.tight_layout()
    fig.savefig(out_png, dpi=150, bbox_inches="tight")
    plt.close(fig)

    summary = {
        "timestamp": stamp,
        "cpu_count": os.cpu_count(),
        "n_jobs_list": n_jobs_list,
        "repeats": args.repeats,
        "results": results,
        "chart_png": str(out_png),
    }
    out_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("\n" + "=" * 60)
    print(f"Gráfico: {out_png}")
    print(f"Dados:   {out_json}")
    for label, rows in results.items():
        best = min(rows, key=lambda r: r["best_seconds"])
        print(
            f"  {label}: ótimo n_jobs={best['n_jobs']} → {best['best_seconds']:.3f}s "
            f"(vs n_jobs=1: {next(r for r in rows if r['n_jobs']==1)['best_seconds']:.3f}s)"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
