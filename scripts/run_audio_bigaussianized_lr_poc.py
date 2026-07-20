#!/usr/bin/env python3
"""POC: meta-classifier + bi-Gaussianized LR (Morrison) for audio spoofing detectors.

Reuses an existing score matrix produced by run_audio_spoofing_score_matrix.py.
Default split: 75/38/37 per class (150 total per class) when manifest was built with --with-splits.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

import sys

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "src" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from audio_lr_dataset_utils import DETECTORS, write_json  # noqa: E402
from core.synthetic_lr_reference import (  # noqa: E402
    _classifier_decision_scores,
    _fit_bigauss,
    _plot_distribution,
    _plot_tippett,
    _score_dataframe,
)

FEATURE_SUFFIX = "_bonafide_logit"


def _logit_prob(series: pd.Series, eps: float = 1e-6) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce").clip(eps, 1.0 - eps)
    return np.log(values / (1.0 - values))


def build_features(df: pd.DataFrame, detectors: tuple[str, ...]) -> tuple[pd.DataFrame, list[str]]:
    features = pd.DataFrame(index=df.index)
    for detector in detectors:
        logit_col = f"{detector}{FEATURE_SUFFIX}"
        prob_col = f"{detector}_bonafide_prob"
        if logit_col in df.columns and df[logit_col].notna().any():
            features[logit_col] = pd.to_numeric(df[logit_col], errors="coerce")
        elif prob_col in df.columns:
            features[logit_col] = _logit_prob(df[prob_col])
        else:
            raise RuntimeError(f"Colunas ausentes para detector {detector}")
    feature_cols = [col for col in features.columns if features[col].notna().any()]
    if not feature_cols:
        raise RuntimeError("Nenhuma feature de detector disponível")
    return features, feature_cols


def _purpose_to_split(purpose: str) -> str:
    mapping = {
        "calibration_train": "train_logreg",
        "calibration_bigauss": "calibration_bigauss",
        "evaluation": "test_bigauss",
    }
    return mapping.get(purpose, purpose)


def prepare_dataframe(path: Path, detectors: tuple[str, ...]) -> pd.DataFrame:
    df = pd.read_csv(path, low_memory=False)
    df = df[df["error"].fillna("").eq("")].copy()
    if "y_spoof" not in df.columns:
        df["y_spoof"] = (df["label"].astype(str).str.lower() == "spoof").astype(int)
    df["y_fake"] = df["y_spoof"].astype(int)
    if "reference_split" not in df.columns and "purpose" in df.columns:
        df["reference_split"] = df["purpose"].map(_purpose_to_split)
    elif "reference_split" in df.columns:
        df["reference_split"] = df["reference_split"].map(_purpose_to_split).fillna(df["reference_split"])
    elif "purpose" in df.columns:
        df["reference_split"] = df["purpose"].map(_purpose_to_split)
    features, feature_cols = build_features(df, detectors)
    for col in feature_cols:
        df[col] = features[col]
    return df


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--score-matrix", required=True)
    parser.add_argument("--out-dir", default="outputs/lr_calibration/audio_spoofing/poc")
    parser.add_argument(
        "--detectors",
        default=",".join(DETECTORS),
        help="Detectores separados por vírgula",
    )
    parser.add_argument("--seed", type=int, default=20260704)
    args = parser.parse_args()

    detectors = tuple(item.strip() for item in args.detectors.split(",") if item.strip())
    df = prepare_dataframe(Path(args.score_matrix), detectors)
    _, feature_cols = build_features(df, detectors)

    train = df[df["reference_split"].eq("train_logreg")].copy()
    if train.empty:
        raise RuntimeError(
            "Nenhuma linha train_logreg. Gere manifest com --with-splits ou defina reference_split."
        )
    x_train = train[feature_cols].to_numpy(dtype=float)
    y_train = (1 - train["y_fake"].astype(int)).to_numpy()  # 1 = bonafide/real

    model = LogisticRegression(
        C=1.0,
        class_weight="balanced",
        max_iter=2000,
        solver="lbfgs",
        random_state=args.seed,
    )
    model.fit(x_train, y_train)

    split = df.copy()
    calibration = _fit_bigauss(split, model, feature_cols)
    scored = _score_dataframe(split, model, calibration, feature_cols)

    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    test = scored[scored["reference_split"].eq("test_bigauss")].copy()
    y_test = (1 - test["y_fake"].astype(int)).to_numpy()
    z_test = _classifier_decision_scores(model, test[feature_cols].to_numpy(dtype=float))
    auc = float(roc_auc_score(y_test, z_test)) if len(set(y_test.tolist())) == 2 else float("nan")

    artifact = {
        "model": model,
        "calibration": {
            key: value
            for key, value in calibration.items()
            if key not in {"empirical_cdf", "inv_cdf"}
        },
        "feature_cols": feature_cols,
        "detectors": detectors,
        "hypothesis_positive": "bonafide",
        "llr_base": "natural_log",
    }
    model_path = out_dir / "audio_spoofing_lr_model.joblib"
    joblib.dump(artifact, model_path)

    _plot_tippett(out_dir / "lr_reference_tippett.png", test, "POC audio spoofing — Tippett (teste)")
    _plot_distribution(out_dir / "lr_reference_distribution.png", test, "POC audio spoofing — distribuição LR (teste)")
    scored.to_csv(out_dir / "lr_reference_scored.csv", index=False)
    test.to_csv(out_dir / "lr_reference_test_scored.csv", index=False)

    report = {
        "score_matrix": str(args.score_matrix),
        "model_path": str(model_path),
        "detectors": detectors,
        "feature_cols": feature_cols,
        "train_rows": int(len(train)),
        "test_rows": int(len(test)),
        "train_class_counts": train["y_fake"].value_counts().sort_index().to_dict(),
        "test_auc_real_vs_spoof": auc,
        "calibration_eer": calibration.get("eer"),
        "calibration_sigma": calibration.get("sigma"),
    }
    write_json(out_dir / "lr_reference_report.json", report)
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
