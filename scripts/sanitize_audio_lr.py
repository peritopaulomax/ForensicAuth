#!/usr/bin/env python3
"""Sanitize the audio spoofing LR score matrix.

Removes duplicated rows (same dataset/generator/label/source_id) keeping the row
with complete finite detector scores, and separates rows with NaN/placeholder
logits into a re-score worklist. Writes a cleaned matrix (only complete, unique
scored rows) plus a JSON report. This is deterministic and idempotent: running it
twice on the cleaned matrix is a no-op.
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

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src" / "backend"))

from audio_lr_dataset_utils import DETECTORS  # noqa: E402
from core.latent_typicality.representations_utils import source_id_stem  # noqa: E402

LOGIT_COLS = [f"{det}_bonafide_logit" for det in DETECTORS]


def _finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _is_blank(value: Any) -> bool:
    """True for None, NaN, empty string, or the literal 'nan' text."""
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    text = str(value).strip()
    return text == "" or text.lower() == "nan"


def _row_complete(row: dict[str, Any]) -> bool:
    return all(_finite(row.get(col)) for col in LOGIT_COLS)


def _canonical_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(row.get("dataset", "")),
        str(row.get("generator", "")),
        str(row.get("label", "")).strip().lower(),
        source_id_stem(str(row.get("source_id", ""))),
    )


def sanitize(score_matrix: Path) -> dict[str, Any]:
    df = pd.read_csv(score_matrix, low_memory=False)
    total = len(df)

    records = df.to_dict(orient="records")
    error_rows = [r for r in records if not _is_blank(r.get("error"))]
    ok_rows = [r for r in records if _is_blank(r.get("error"))]

    complete: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    nan_worklist: list[dict[str, Any]] = []
    dup_removed = 0

    for row in ok_rows:
        key = _canonical_key(row)
        if _row_complete(row):
            if key in complete:
                dup_removed += 1  # duplicate complete row -> keep first, drop the rest
                continue
            complete[key] = row
        else:
            nan_worklist.append(row)

    # NaN rows whose canonical key is already satisfied by a complete row are pure
    # duplicates and can be dropped; the rest need re-scoring.
    real_worklist: list[dict[str, Any]] = []
    nan_dropped_dup = 0
    seen_worklist_keys: set[tuple[str, str, str, str]] = set()
    for row in nan_worklist:
        key = _canonical_key(row)
        if key in complete:
            nan_dropped_dup += 1
            continue
        if key in seen_worklist_keys:
            nan_dropped_dup += 1
            continue
        seen_worklist_keys.add(key)
        real_worklist.append(row)

    # Error rows are files that failed detector scoring (typically deterministic
    # "padded input size" on too-short audio). They carry no scores, are dropped
    # from the matrix, and recorded in an unusable ledger so the selection lock
    # never re-selects them (it picks replacements from the pool instead).
    complete_df = pd.DataFrame(list(complete.values()))
    clean_df = complete_df.copy()

    unusable_rows = [
        {
            "dataset": r.get("dataset", ""),
            "generator": r.get("generator", ""),
            "label": str(r.get("label", "")).strip().lower(),
            "source_id": source_id_stem(str(r.get("source_id", ""))),
            "error": str(r.get("error", "")),
        }
        for r in error_rows
    ]

    per_group = (
        complete_df.groupby(["dataset", "generator", "label"]).size().reset_index(name="complete_unique")
        if not complete_df.empty
        else pd.DataFrame()
    )

    report = {
        "score_matrix": str(score_matrix),
        "rows_before": total,
        "error_rows": len(error_rows),
        "complete_unique_rows": len(complete),
        "duplicate_complete_removed": dup_removed,
        "nan_rows_total": len(nan_worklist),
        "nan_rows_to_rescore": len(real_worklist),
        "nan_rows_dropped_as_dup": nan_dropped_dup,
        "rows_after_clean": len(clean_df),
    }
    return {
        "clean_df": clean_df,
        "worklist": pd.DataFrame(real_worklist),
        "unusable": pd.DataFrame(unusable_rows),
        "per_group": per_group,
        "report": report,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--score-matrix",
        default="outputs/lr_calibration/audio_spoofing/score_matrices/lr_scores_balanced_full.csv",
    )
    parser.add_argument("--no-backup", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Report only, do not overwrite matrix")
    args = parser.parse_args()

    score_matrix = ROOT / args.score_matrix
    if not score_matrix.is_file():
        print(f"Score matrix nao encontrada: {score_matrix}", flush=True)
        return 2

    result = sanitize(score_matrix)
    report = result["report"]

    out_dir = score_matrix.parent
    worklist_path = out_dir / "sanitize_nan_worklist.csv"
    report_path = out_dir / "sanitize_report.json"
    inv_dir = ROOT / "outputs/lr_calibration/audio_spoofing/inventory"
    unusable_path = inv_dir / "unusable_source_ids.csv"

    if not args.dry_run:
        if not args.no_backup:
            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            shutil.copy2(score_matrix, score_matrix.with_suffix(f".csv.bak-sanitize-{ts}"))
        result["clean_df"].to_csv(score_matrix, index=False)
        if not result["worklist"].empty:
            result["worklist"].to_csv(worklist_path, index=False)
            report["nan_worklist_csv"] = str(worklist_path)
        # Merge (union) the unusable ledger so short/unscoreable files are never
        # re-selected across sanitize runs.
        new_unusable = result["unusable"]
        if not new_unusable.empty:
            inv_dir.mkdir(parents=True, exist_ok=True)
            if unusable_path.is_file():
                prev = pd.read_csv(unusable_path, low_memory=False)
                merged = pd.concat([prev, new_unusable], ignore_index=True)
            else:
                merged = new_unusable
            merged = merged.drop_duplicates(subset=["dataset", "generator", "label", "source_id"])
            merged.to_csv(unusable_path, index=False)
            report["unusable_ledger"] = str(unusable_path)
            report["unusable_total"] = int(len(merged))
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
