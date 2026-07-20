#!/usr/bin/env python3
"""Merge augmented audio spoofing scores into the reference score matrix."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def merge_audio_augmented_scores(
    *,
    reference: Path,
    augmented: Path,
    out: Path,
) -> dict[str, int | str]:
    ref = pd.read_csv(reference, low_memory=False)
    aug = pd.read_csv(augmented, low_memory=False)
    if "augmentation" not in ref.columns:
        ref["augmentation"] = ""
    else:
        ref["augmentation"] = ref["augmentation"].fillna("").astype(str)
    if "augmentation" not in aug.columns:
        raise ValueError("Score matrix aumentado deve conter coluna 'augmentation'")
    merged = pd.concat([ref, aug], ignore_index=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(out, index=False)
    summary = {
        "reference_rows": int(len(ref)),
        "augmented_rows": int(len(aug)),
        "merged_rows": int(len(merged)),
        "reference_path": str(reference),
        "augmented_path": str(augmented),
        "out_path": str(out),
    }
    out.with_suffix(".summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
    return summary


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reference",
        default=str(root / "outputs/lr_calibration/audio_spoofing/score_matrices/lr_scores_balanced_full.csv"),
    )
    parser.add_argument("--augmented", required=True, type=Path)
    parser.add_argument(
        "--out",
        default=str(
            root / "outputs/lr_calibration/audio_spoofing/score_matrices/lr_scores_balanced_full_augmented.csv"
        ),
    )
    args = parser.parse_args()
    summary = merge_audio_augmented_scores(
        reference=Path(args.reference),
        augmented=Path(args.augmented),
        out=Path(args.out),
    )
    print(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False))


if __name__ == "__main__":
    main()
