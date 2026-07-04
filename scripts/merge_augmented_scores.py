#!/usr/bin/env python3
"""Merge an augmented score matrix into the reference score matrix.

Usage example:
    python scripts/merge_augmented_scores.py \\
        --reference outputs/lr_calibration/score_matrices/lr_scores_balanced_full.csv \\
        --augmented /home/bfl-pcf/datasets/defactify_lr_sample_augmented/scores.csv \\
        --out outputs/lr_calibration/score_matrices/lr_scores_balanced_full_augmented.csv
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", required=True, type=Path)
    parser.add_argument("--augmented", required=True, action="append", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--tag-augmentation", action="store_true", default=True)
    args = parser.parse_args()

    ref = pd.read_csv(args.reference, low_memory=False)
    frames = [ref]
    total_augmented = 0
    for aug_path in args.augmented:
        aug = pd.read_csv(aug_path, low_memory=False)
        if args.tag_augmentation:
            ref["augmentation"] = ref.get("augmentation", "")
            if "augmentation" not in aug.columns:
                aug["augmentation"] = ""
        frames.append(aug)
        total_augmented += len(aug)

    merged = pd.concat(frames, ignore_index=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(args.out, index=False)

    summary = {
        "reference_rows": int(len(ref)),
        "augmented_rows": int(total_augmented),
        "merged_rows": int(len(merged)),
        "reference_path": str(args.reference),
        "augmented_paths": [str(p) for p in args.augmented],
        "out_path": str(args.out),
    }
    args.out.with_suffix(".summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
