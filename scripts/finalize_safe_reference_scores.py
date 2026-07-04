"""Finalize the SAFE-augmented reference score matrix.

Backs up the old matrix, replaces it with the new one, and updates the
summary JSON.
"""

from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MATRIX_DIR = ROOT / "outputs" / "lr_calibration" / "score_matrices"
OLD_CSV = MATRIX_DIR / "lr_scores_balanced_full.csv"
NEW_CSV = MATRIX_DIR / "lr_scores_balanced_full_safe_new.csv"
SUMMARY = MATRIX_DIR / "lr_scores_balanced_full.summary.json"


def main() -> int:
    if not NEW_CSV.is_file():
        print(f"New CSV not found: {NEW_CSV}", file=sys.stderr)
        return 1

    df = pd.read_csv(NEW_CSV, low_memory=False)
    safe_errors = int(df["safe_error"].fillna("").ne("").sum())
    safe_mean_fake = float(df[df["safe_error"].eq("")]["safe_fake_prob"].mean())

    backup = OLD_CSV.with_suffix(f".backup.{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}.csv")
    if OLD_CSV.is_file():
        shutil.copy2(OLD_CSV, backup)
        print(f"Backed up old matrix to {backup}")

    shutil.move(str(NEW_CSV), str(OLD_CSV))
    print(f"Replaced {OLD_CSV}")

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rows": int(len(df)),
        "columns": int(len(df.columns)),
        "safe_errors": safe_errors,
        "safe_mean_fake_prob": round(safe_mean_fake, 6),
        "detectors": [c.replace("_fake_prob", "") for c in df.columns if c.endswith("_fake_prob")],
        "source": str(OLD_CSV),
    }
    SUMMARY.write_text(json.dumps(summary, indent=2) + "\n")
    print(f"Updated summary: {SUMMARY}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
