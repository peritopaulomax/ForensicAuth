#!/usr/bin/env python3
"""Merge corrected Fake-or-Real scores/manifest into the full LR calibration artifacts."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASET = "Fake-or-Real"


def _backup(path: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = path.with_suffix(path.suffix + f".bak-for-{stamp}")
    shutil.copy2(path, backup)
    return backup


def merge_score_matrix(
    full_csv: Path,
    fixed_csv: Path,
    *,
    backup: bool = True,
) -> dict[str, int]:
    full = pd.read_csv(full_csv, low_memory=False)
    fixed = pd.read_csv(fixed_csv, low_memory=False)
    if backup:
        print(f"Backup scores: {_backup(full_csv)}")
    kept = full[full["dataset"] != DATASET].copy()
    merged = pd.concat([kept, fixed], ignore_index=True)
    merged.to_csv(full_csv, index=False)
    return {
        "full_rows_before": len(full),
        "fake_or_real_removed": int((full["dataset"] == DATASET).sum()),
        "fake_or_real_added": len(fixed),
        "full_rows_after": len(merged),
    }


def merge_manifest(
    full_manifest: Path,
    fixed_manifest: Path,
    *,
    backup: bool = True,
) -> dict[str, int]:
    full = pd.read_csv(full_manifest, low_memory=False)
    fixed = pd.read_csv(fixed_manifest, low_memory=False)
    if backup:
        print(f"Backup manifest: {_backup(full_manifest)}")
    kept = full[full["dataset"] != DATASET].copy()
    merged = pd.concat([kept, fixed], ignore_index=True)
    merged.to_csv(full_manifest, index=False)
    return {
        "manifest_rows_before": len(full),
        "fake_or_real_removed": int((full["dataset"] == DATASET).sum()),
        "fake_or_real_added": len(fixed),
        "manifest_rows_after": len(merged),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--full-scores",
        default=str(
            PROJECT_ROOT
            / "outputs/lr_calibration/audio_spoofing/score_matrices/lr_scores_balanced_full.csv"
        ),
    )
    parser.add_argument(
        "--fixed-scores",
        default=str(
            PROJECT_ROOT
            / "outputs/lr_calibration/audio_spoofing/score_matrices/lr_scores_fake_or_real_fixed.csv"
        ),
    )
    parser.add_argument(
        "--full-manifest",
        default=str(
            PROJECT_ROOT / "outputs/lr_calibration/audio_spoofing/samples/full/manifest.csv"
        ),
    )
    parser.add_argument(
        "--fixed-manifest",
        default=str(
            PROJECT_ROOT
            / "outputs/lr_calibration/audio_spoofing/samples/fake_or_real_fixed/manifest.csv"
        ),
    )
    parser.add_argument("--no-backup", action="store_true")
    args = parser.parse_args()

    fixed_scores = Path(args.fixed_scores)
    fixed_manifest = Path(args.fixed_manifest)
    if not fixed_scores.is_file():
        raise FileNotFoundError(f"Scores corrigidos ausentes: {fixed_scores}")
    if not fixed_manifest.is_file():
        raise FileNotFoundError(f"Manifest corrigido ausente: {fixed_manifest}")

    report = {
        "scores": merge_score_matrix(
            Path(args.full_scores),
            fixed_scores,
            backup=not args.no_backup,
        ),
        "manifest": merge_manifest(
            Path(args.full_manifest),
            fixed_manifest,
            backup=not args.no_backup,
        ),
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
