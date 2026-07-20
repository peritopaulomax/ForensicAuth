#!/usr/bin/env python3
"""Repair stale/NaN detector scores in the LR representations matrix.

Root cause handled here: the extraction step, when resumed, skips samples whose
``.npy`` embeddings already exist on disk and keeps their (possibly stale) CSV row.
Some of those rows carry NaN detector scores from an earlier buggy extraction, even
though the *sanitized* score matrix has finite scores for the same physical audio.
The latent-typicality ``S_{detector}`` features read the score straight from the
representations row (``row["{detector}_bonafide_logit"]``), so those NaNs reach the
LogisticRegression and crash calibration.

Two deterministic, idempotent operations aligned with the sanitized score matrix:

1. Backfill the per-detector score columns (``bonafide_logit``, ``bonafide_prob``,
   ``spoof_logit``) for representation rows that currently have a non-finite
   ``bonafide_logit`` whenever a *complete finite* row exists in the sanitized score
   matrix for the same (dataset, generator, label, source_id_stem). The detector
   score is a property of the physical audio file, so the backfilled value is exact.

2. Drop rows belonging to *orphan generator groups*: pairs (dataset, generator) that
   exist in the representations matrix but are absent from the sanitized score matrix.
   Those are stale/superseded pools (renamed generators such as ``OpenAI`` ->
   ``OpenAI_fixed``, bonafide pools already accounted for under the spoof generators,
   or parsing artifacts) that are not part of the selected reference population.

Applies the same repair to the merged ``representations.csv`` and the
``originals/representations.csv``. Writes timestamped backups and a JSON report.
Re-running on already-clean files is a no-op.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "backend"))

from core.latent_typicality.representations_utils import source_id_stem  # noqa: E402

DETECTORS = ("df_arena_1b", "sls_xlsr", "wedefense_wavlm_mhfa")
# Columns copied from the score matrix into a representations row on backfill. Only
# these detector-score columns exist in both files and can go stale/NaN; embedding
# paths/dims are never touched (the .npy files are already on disk).
SCORE_COLS = [
    f"{det}_{suffix}"
    for det in DETECTORS
    for suffix in ("bonafide_logit", "bonafide_prob", "spoof_logit")
]
LOGIT_COLS = [f"{det}_bonafide_logit" for det in DETECTORS]

DEFAULT_BASE = "outputs/lr_calibration/audio_spoofing"


def _finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _key(dataset: Any, generator: Any, label: Any, source_id: Any) -> tuple[str, str, str, str]:
    return (
        str(dataset),
        str(generator),
        str(label).strip().lower(),
        source_id_stem(str(source_id)),
    )


def _build_matrix_lookup(matrix: pd.DataFrame) -> dict[tuple[str, str, str, str], dict[str, Any]]:
    """Map (dataset, generator, label, source_id_stem) -> score columns, complete rows only."""
    lookup: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    have = [c for c in SCORE_COLS if c in matrix.columns]
    for row in matrix.to_dict(orient="records"):
        if not all(_finite(row.get(c)) for c in LOGIT_COLS):
            continue
        key = _key(row.get("dataset"), row.get("generator"), row.get("label"), row.get("source_id"))
        if key not in lookup:
            lookup[key] = {c: row.get(c) for c in have}
    return lookup


def repair_frame(
    rep: pd.DataFrame,
    lookup: dict[tuple[str, str, str, str], dict[str, Any]],
    matrix_groups: set[tuple[str, str]],
) -> dict[str, Any]:
    """Return repaired frame + counters. Pure function (does not touch disk)."""
    rep = rep.copy()

    # Step 2 first: identify orphan generator groups (present here, absent in matrix).
    rep_groups = set(zip(rep["dataset"].astype(str), rep["generator"].astype(str)))
    orphan_groups = sorted(rep_groups - matrix_groups)
    orphan_pairs = set(orphan_groups)
    orphan_mask = rep.apply(
        lambda r: (str(r["dataset"]), str(r["generator"])) in orphan_pairs, axis=1
    )
    orphan_rows_removed = int(orphan_mask.sum())
    kept = rep.loc[~orphan_mask].copy()

    # Step 1: backfill NaN logit rows from the score matrix (exact key match).
    logit_vals = kept[LOGIT_COLS].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    nan_mask = pd.Series(~np.isfinite(logit_vals).all(axis=1), index=kept.index)

    have = [c for c in SCORE_COLS if c in kept.columns]
    backfilled = 0
    unresolved: list[tuple[str, str, str, str]] = []
    for idx in kept.index[nan_mask]:
        r = kept.loc[idx]
        key = _key(r["dataset"], r["generator"], r["label"], r["source_id"])
        src = lookup.get(key)
        if src is None:
            unresolved.append(key)
            continue
        for c in have:
            kept.at[idx, c] = src.get(c)
        backfilled += 1

    return {
        "frame": kept,
        "orphan_groups": orphan_groups,
        "orphan_rows_removed": orphan_rows_removed,
        "nan_rows_before": int(nan_mask.sum()),
        "backfilled_rows": backfilled,
        "unresolved_keys": [list(k) for k in unresolved],
    }


def _process_file(
    path: Path,
    lookup: dict[tuple[str, str, str, str], dict[str, Any]],
    matrix_groups: set[tuple[str, str]],
    *,
    dry_run: bool,
    no_backup: bool,
) -> dict[str, Any]:
    df = pd.read_csv(path, low_memory=False)
    result = repair_frame(df, lookup, matrix_groups)
    frame = result.pop("frame")
    result["path"] = str(path)
    result["rows_before"] = len(df)
    result["rows_after"] = len(frame)

    changed = result["orphan_rows_removed"] > 0 or result["backfilled_rows"] > 0
    if not dry_run and changed:
        if not no_backup:
            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            shutil.copy2(path, path.with_suffix(f".csv.bak-reprscore-{ts}"))
        frame.to_csv(path, index=False)
        result["written"] = True
    else:
        result["written"] = False
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default=DEFAULT_BASE, help="LR audio-spoofing output base dir")
    parser.add_argument("--dry-run", action="store_true", help="Report only, do not write")
    parser.add_argument("--no-backup", action="store_true")
    args = parser.parse_args()

    base = ROOT / args.base
    matrix_path = base / "score_matrices" / "lr_scores_balanced_full.csv"
    merged_path = base / "representations" / "representations.csv"
    originals_path = base / "representations" / "originals" / "representations.csv"

    if not matrix_path.is_file():
        print(f"Score matrix nao encontrada: {matrix_path}", flush=True)
        return 2

    matrix = pd.read_csv(matrix_path, low_memory=False)
    if "error" in matrix.columns:
        blank = matrix["error"].isna() | matrix["error"].astype(str).str.strip().isin(["", "nan"])
        matrix = matrix[blank].copy()
    lookup = _build_matrix_lookup(matrix)
    matrix_groups = set(zip(matrix["dataset"].astype(str), matrix["generator"].astype(str)))

    report: dict[str, Any] = {
        "score_matrix": str(matrix_path),
        "matrix_complete_keys": len(lookup),
        "matrix_groups": len(matrix_groups),
        "dry_run": args.dry_run,
        "files": [],
    }
    for path in (merged_path, originals_path):
        if not path.is_file():
            report["files"].append({"path": str(path), "missing": True})
            continue
        report["files"].append(
            _process_file(
                path, lookup, matrix_groups, dry_run=args.dry_run, no_backup=args.no_backup
            )
        )

    if not args.dry_run:
        report_path = base / "representations" / "repair_representations_report.json"
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        report["report_path"] = str(report_path)

    print(json.dumps(report, indent=2, ensure_ascii=False))

    unresolved = sum(len(f.get("unresolved_keys", [])) for f in report["files"] if isinstance(f, dict))
    return 1 if unresolved else 0


if __name__ == "__main__":
    raise SystemExit(main())
