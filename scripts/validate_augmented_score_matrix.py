#!/usr/bin/env python3
"""Validate the merged augmented score matrix."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix", required=True, type=Path)
    parser.add_argument("--expected-rows", type=int, default=255000)
    parser.add_argument("--expected-augmentations", type=int, default=8)
    args = parser.parse_args()

    if not args.matrix.exists():
        print(f"[ERROR] Matrix not found: {args.matrix}")
        return 1

    df = pd.read_csv(args.matrix, low_memory=False)
    total_rows = len(df)
    print(f"Total rows: {total_rows}")

    # Required columns
    required = {
        "dataset",
        "purpose",
        "generator",
        "label",
        "augmentation",
        "safe_fake_prob",
        "safe_real_prob",
        "safe_raw_score",
        "safe_decision",
        "safe_device",
    }
    missing = required - set(df.columns)
    if missing:
        print(f"[ERROR] Missing columns: {missing}")
        return 1
    print("All required columns present.")

    # Augmentation distribution
    aug_counts = df["augmentation"].fillna("(original)").value_counts().to_dict()
    print("Augmentation distribution:")
    for aug, count in sorted(aug_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  {aug}: {count}")

    # Check for duplicates based on image_sha256 + augmentation + dataset
    dup_cols = ["image_sha256", "augmentation", "dataset"]
    available_dup_cols = [c for c in dup_cols if c in df.columns]
    if available_dup_cols:
        n_dups = df.duplicated(subset=available_dup_cols).sum()
        print(f"Duplicate rows ({'+'.join(available_dup_cols)}): {n_dups}")
        if n_dups > 0:
            print("[WARN] Duplicates found.")

    # SAFE probabilities within [0, 1]
    for col in ["safe_fake_prob", "safe_real_prob"]:
        if col in df.columns:
            invalid = df[(df[col] < 0) | (df[col] > 1)]
            if len(invalid):
                print(f"[ERROR] {col} has {len(invalid)} values outside [0,1]")
                return 1
            print(f"{col}: OK [0,1]")

    # Row count check (with tolerance)
    tolerance = args.expected_rows * 0.05
    if abs(total_rows - args.expected_rows) > tolerance:
        print(f"[WARN] Row count {total_rows} deviates from expected {args.expected_rows} by >5%")
    else:
        print(f"Row count within 5% of expected {args.expected_rows}.")

    print("Validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
