#!/usr/bin/env python3
"""Compare LR calibration metrics with and without augmented variants.

Example:
    python scripts/evaluate_augmentation_impact.py \\
        --reference outputs/lr_calibration/score_matrices/lr_scores_balanced_full.csv \\
        --augmented outputs/lr_calibration/score_matrices/lr_scores_balanced_full_augmented.csv \\
        --out-dir outputs/lr_calibration/augmentation_impact
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "src" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from core.synthetic_lr_reference import (  # noqa: E402
    ALL_DETECTORS,
    DEFAULT_META_CLASSIFIER,
    _assign_splits,
    _build_reference_sample,
    _cllr_ln,
    _eer,
    _feature_cols,
    _fit_bigauss,
    _load_scores,
    _metrics,
    _score_dataframe,
    _train_meta_classifier,
    normalize_reference_selection,
)


def _evaluate_score_matrix(score_matrix: Path, selection: Any, seed: int, classifier: str) -> dict[str, Any]:
    selected_detectors = tuple(d for d in ALL_DETECTORS)
    feature_cols = _feature_cols(selected_detectors)
    items = normalize_reference_selection(selection)
    df = _load_scores(score_matrix)
    sample = _build_reference_sample(df, items, seed)
    split = _assign_splits(sample, seed)

    train = split[split["reference_split"].eq("train_logreg")]
    x_train = train[feature_cols].to_numpy(dtype=float)
    y_train = (1 - train["y_fake"].astype(int)).to_numpy()

    model = _train_meta_classifier(classifier, x_train, y_train, feature_cols, seed)
    calibration = _fit_bigauss(split, model, feature_cols)
    scored = _score_dataframe(split, model, calibration, feature_cols)
    test = scored[scored["reference_split"].eq("test_bigauss")].copy()

    return {
        "score_matrix": str(score_matrix),
        "selection": selection,
        "classifier": classifier,
        "seed": seed,
        "train_rows": int(len(train)),
        "test_rows": int(len(test)),
        "metrics": _metrics(test),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", required=True, type=Path)
    parser.add_argument("--augmented", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--selection", default='{"macro": "diffusion_cnn_modern"}')
    parser.add_argument("--seed", type=int, default=20260630)
    parser.add_argument("--classifier", default=DEFAULT_META_CLASSIFIER)
    args = parser.parse_args()

    selection = json.loads(args.selection)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    baseline = _evaluate_score_matrix(args.reference, selection, args.seed, args.classifier)
    augmented = _evaluate_score_matrix(args.augmented, selection, args.seed, args.classifier)

    report = {
        "selection": selection,
        "classifier": args.classifier,
        "seed": args.seed,
        "baseline": baseline,
        "augmented": augmented,
        "delta": {
            key: round(augmented["metrics"][key] - baseline["metrics"][key], 6)
            for key in baseline["metrics"]
            if isinstance(baseline["metrics"][key], (int, float)) and not math.isnan(baseline["metrics"][key])
        },
    }

    report_path = args.out_dir / "augmentation_impact_report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))


if __name__ == "__main__":
    main()
