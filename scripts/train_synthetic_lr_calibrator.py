#!/usr/bin/env python3
"""Train a logistic-regression LR calibrator from detector score matrices."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

DETECTORS = ("ai_image_detector_deploy", "sdxl_flux_detector_v1_1", "bfree", "corvi2023")


def _load(paths: list[str]) -> pd.DataFrame:
    frames = [pd.read_csv(path) for path in paths]
    return pd.concat(frames, ignore_index=True)


def _logit_prob(series: pd.Series, eps: float = 1e-6) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce").clip(eps, 1.0 - eps)
    return np.log(values / (1.0 - values))


def build_features(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    features = pd.DataFrame(index=df.index)
    for detector in DETECTORS:
        prob_col = f"{detector}_fake_prob"
        if prob_col in df:
            features[f"{detector}_logit_prob"] = _logit_prob(df[prob_col])
    feature_cols = list(features.columns)
    feature_cols = [col for col in feature_cols if not features[col].isna().all()]
    if not feature_cols:
        raise RuntimeError("No detector score columns found")
    return features, feature_cols


def _cllr_from_log10_lr(log10_lr: np.ndarray, y: np.ndarray) -> float:
    target = log10_lr[y == 1]
    nontarget = log10_lr[y == 0]
    if len(target) == 0 or len(nontarget) == 0:
        return float("nan")
    c1 = np.log2(1.0 + np.power(10.0, -target))
    c2 = np.log2(1.0 + np.power(10.0, nontarget))
    return float(0.5 * (np.mean(c1) + np.mean(c2)))


def _balanced_dataset_class_weights(train_df: pd.DataFrame) -> np.ndarray:
    group_counts = train_df.groupby(["dataset", "y_fake"]).size()
    weights = train_df.apply(
        lambda row: 1.0 / float(group_counts.loc[(row["dataset"], row["y_fake"])]),
        axis=1,
    ).to_numpy(dtype=float)
    return weights / np.mean(weights)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--score-matrix", action="append", required=True)
    parser.add_argument("--out-dir", default="/home/bfl-pcf/VA Suite/outputs/lr_calibration/models")
    parser.add_argument("--model-name", default="synthetic_lr_calibrator.joblib")
    parser.add_argument("--train-purpose", default="calibration_train")
    parser.add_argument("--include-dataset", action="append", default=[])
    parser.add_argument("--exclude-dataset", action="append", default=[])
    parser.add_argument("--balance-dataset-class", action="store_true")
    parser.add_argument("--c", type=float, default=1.0)
    parser.add_argument("--max-iter", type=int, default=2000)
    args = parser.parse_args()

    df = _load(args.score_matrix)
    train_df = df[(df["purpose"] == args.train_purpose) & (df.get("error", "").fillna("") == "")].copy()
    if args.include_dataset:
        train_df = train_df[train_df["dataset"].isin(args.include_dataset)].copy()
    if args.exclude_dataset:
        train_df = train_df[~train_df["dataset"].isin(args.exclude_dataset)].copy()
    if train_df.empty:
        raise RuntimeError(f"No rows with purpose={args.train_purpose}")
    y = train_df["y_fake"].astype(int).to_numpy()
    if len(set(y.tolist())) < 2:
        raise RuntimeError("Training data must contain both real and fake rows")

    x, feature_cols = build_features(train_df)
    pipeline = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            (
                "model",
                LogisticRegression(
                    C=args.c,
                    class_weight="balanced",
                    max_iter=args.max_iter,
                    solver="lbfgs",
                    random_state=20260629,
                ),
            ),
        ]
    )
    sample_weight = _balanced_dataset_class_weights(train_df) if args.balance_dataset_class else None
    fit_kwargs = {"model__sample_weight": sample_weight} if sample_weight is not None else {}
    pipeline.fit(x[feature_cols], y, **fit_kwargs)
    prob = pipeline.predict_proba(x[feature_cols])[:, 1]
    logit = np.log(np.clip(prob, 1e-12, 1 - 1e-12) / np.clip(1 - prob, 1e-12, 1))
    log10_lr = logit / math.log(10.0)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    artifact = {
        "pipeline": pipeline,
        "feature_cols": feature_cols,
        "detectors": DETECTORS,
        "hypothesis_positive": "fake",
        "llr_base": "log10",
        "train_purpose": args.train_purpose,
    }
    model_path = out_dir / args.model_name
    joblib.dump(artifact, model_path)

    model = pipeline.named_steps["model"]
    report = {
        "model_path": str(model_path),
        "rows": int(len(train_df)),
        "class_counts": train_df["y_fake"].value_counts().sort_index().to_dict(),
        "dataset_counts": train_df["dataset"].value_counts().sort_index().to_dict(),
        "dataset_class_counts": {
            f"{dataset}/{label}": int(count)
            for (dataset, label), count in train_df.groupby(["dataset", "y_fake"]).size().items()
        },
        "balance_dataset_class": bool(args.balance_dataset_class),
        "feature_cols": feature_cols,
        "coefficients": dict(zip(feature_cols, model.coef_[0].tolist())),
        "intercept": float(model.intercept_[0]),
        "train_auc": float(roc_auc_score(y, prob)) if len(set(y.tolist())) == 2 else None,
        "train_cllr": _cllr_from_log10_lr(log10_lr, y),
    }
    report_path = model_path.with_suffix(".report.json")
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
