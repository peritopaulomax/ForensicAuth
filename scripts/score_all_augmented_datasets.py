#!/usr/bin/env python3
"""Score all augmented LR datasets sequentially and merge into the reference matrix."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "src" / "backend"
SCORER = ROOT / "scripts" / "run_lr_score_matrix_batched_v2.py"
MERGER = ROOT / "scripts" / "merge_augmented_scores.py"
REFERENCE = ROOT / "outputs" / "lr_calibration" / "score_matrices" / "lr_scores_balanced_full.csv"
FINAL = ROOT / "outputs" / "lr_calibration" / "score_matrices" / "lr_scores_balanced_full_augmented.csv"

DATASETS = [
    ("defactify_lr_sample_augmented", "/home/bfl-pcf/datasets/defactify_lr_sample_augmented"),
    ("genimage_lr_sample_augmented", "/home/bfl-pcf/datasets/genimage_lr_sample_augmented"),
    ("aigcdetectbenchmark_lr_sample_augmented", "/home/bfl-pcf/datasets/aigcdetectbenchmark_lr_sample_augmented"),
    ("opensdi_lr_sample_augmented", "/home/bfl-pcf/datasets/opensdi_lr_sample_augmented"),
    ("aigibench_lr_sample_augmented", "/home/bfl-pcf/datasets/aigibench_lr_sample_augmented"),
    ("aigibench_socialrf_lr_sample_augmented", "/home/bfl-pcf/datasets/aigibench_socialrf_lr_sample_augmented"),
    ("synthbuster_lr_sample_augmented", "/home/bfl-pcf/datasets/synthbuster_lr_sample_augmented"),
    ("bfree_extended_lr_sample_augmented", "/home/bfl-pcf/datasets/bfree_extended_lr_sample_augmented"),
]


def run_scorer(manifest: Path, out: Path, batch_size: int) -> None:
    cmd = [
        sys.executable,
        str(SCORER),
        "--manifest", str(manifest),
        "--out", str(out),
        "--batch-size", str(batch_size),
    ]
    if out.exists():
        cmd.append("--resume")
    print(f"Running: {' '.join(cmd)}", flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True)


def run_merger(augmented_scores: list[Path]) -> None:
    cmd = [
        sys.executable,
        str(MERGER),
        "--reference", str(REFERENCE),
        "--augmented", str(augmented_scores[0]),
        "--out", str(FINAL),
    ]
    for extra in augmented_scores[1:]:
        cmd.extend(["--augmented", str(extra)])
    print(f"Running merger: {' '.join(cmd)}", flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--skip-scoring", action="store_true")
    args = parser.parse_args()

    augmented_scores: list[Path] = []
    for name, base_dir in DATASETS:
        manifest = Path(base_dir) / "manifest.csv"
        out = Path(base_dir) / "scores.csv"
        if not manifest.exists():
            print(f"[SKIP] Manifest not found: {manifest}")
            continue
        if not args.skip_scoring:
            run_scorer(manifest, out, args.batch_size)
        augmented_scores.append(out)

    if augmented_scores:
        run_merger(augmented_scores)
        summary = json.loads(FINAL.with_suffix(".summary.json").read_text(encoding="utf-8"))
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print("No augmented scores to merge.")


if __name__ == "__main__":
    main()
