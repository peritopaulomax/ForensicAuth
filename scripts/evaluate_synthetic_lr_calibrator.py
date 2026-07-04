#!/usr/bin/env python3
"""Evaluate a frozen synthetic-image LR calibrator."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import joblib
import matplotlib
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score, roc_curve

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def _load(paths: list[str]) -> pd.DataFrame:
    frames = [pd.read_csv(path) for path in paths]
    return pd.concat(frames, ignore_index=True)


def _logit_prob(series: pd.Series, eps: float = 1e-6) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce").clip(eps, 1.0 - eps)
    return np.log(values / (1.0 - values))


def _features(df: pd.DataFrame, feature_cols: list[str]) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    for col in feature_cols:
        if col.endswith("_logit_prob"):
            detector = col.removesuffix("_logit_prob")
            out[col] = _logit_prob(df[f"{detector}_fake_prob"])
        elif col.endswith("_raw_score"):
            out[col] = pd.to_numeric(df[col], errors="coerce") if col in df else pd.to_numeric(df[col], errors="coerce")
        else:
            out[col] = pd.to_numeric(df[col], errors="coerce") if col in df else np.nan
    return out[feature_cols]


def cllr_from_log10_lr(log10_lr: np.ndarray, y: np.ndarray) -> float:
    target = log10_lr[y == 1]
    nontarget = log10_lr[y == 0]
    if len(target) == 0 or len(nontarget) == 0:
        return float("nan")
    c1 = np.log2(1.0 + np.power(10.0, -target))
    c2 = np.log2(1.0 + np.power(10.0, nontarget))
    return float(0.5 * (np.mean(c1) + np.mean(c2)))


def min_cllr(scores: np.ndarray, y: np.ndarray) -> float:
    if len(set(y.tolist())) < 2:
        return float("nan")
    order = np.argsort(scores)
    iso = IsotonicRegression(out_of_bounds="clip")
    calibrated = iso.fit_transform(scores[order], y[order])
    restored = np.empty_like(calibrated, dtype=float)
    restored[order] = calibrated
    p = np.clip(restored, 1e-6, 1 - 1e-6)
    return cllr_from_log10_lr(np.log(p / (1 - p)) / math.log(10.0), y)


def eer(y: np.ndarray, scores: np.ndarray) -> float:
    if len(set(y.tolist())) < 2:
        return float("nan")
    fpr, tpr, _thresholds = roc_curve(y, scores)
    fnr = 1 - tpr
    idx = np.nanargmin(np.abs(fnr - fpr))
    return float((fpr[idx] + fnr[idx]) / 2.0)


def _plot_tippett(path: Path, log10_lr: np.ndarray, y: np.ndarray, title: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    plt.figure(figsize=(8, 5))
    for value, label in ((1, "fake"), (0, "real")):
        vals = np.sort(log10_lr[y == value])
        if len(vals) == 0:
            continue
        survival = 1.0 - np.arange(1, len(vals) + 1) / len(vals)
        plt.step(vals, survival, where="post", label=label)
    plt.axvline(0, color="black", linewidth=1, linestyle="--")
    plt.xlabel("log10 LR")
    plt.ylabel("Proportion >= log10 LR")
    plt.title(title)
    plt.legend()
    plt.tight_layout()
    plt.savefig(path)
    plt.close()


def _plot_hist(path: Path, log10_lr: np.ndarray, y: np.ndarray, title: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    plt.figure(figsize=(8, 5))
    bins = np.linspace(float(np.nanmin(log10_lr)), float(np.nanmax(log10_lr)), 40) if len(log10_lr) else 20
    plt.hist(log10_lr[y == 0], bins=bins, alpha=0.6, label="real")
    plt.hist(log10_lr[y == 1], bins=bins, alpha=0.6, label="fake")
    plt.axvline(0, color="black", linewidth=1, linestyle="--")
    plt.xlabel("log10 LR")
    plt.ylabel("count")
    plt.title(title)
    plt.legend()
    plt.tight_layout()
    plt.savefig(path)
    plt.close()


def _metrics(df: pd.DataFrame) -> dict[str, float | int]:
    y = df["y_fake"].astype(int).to_numpy()
    prob = df["lr_fake_probability"].to_numpy()
    log10_lr = df["log10_lr"].to_numpy()
    return {
        "rows": int(len(df)),
        "fake_rows": int(np.sum(y == 1)),
        "real_rows": int(np.sum(y == 0)),
        "auc": float(roc_auc_score(y, prob)) if len(set(y.tolist())) == 2 else float("nan"),
        "eer": eer(y, prob),
        "cllr": cllr_from_log10_lr(log10_lr, y),
        "min_cllr": min_cllr(log10_lr, y),
        "brier": float(brier_score_loss(y, prob)) if len(set(y.tolist())) == 2 else float("nan"),
        "log_loss": float(log_loss(y, prob, labels=[0, 1])) if len(set(y.tolist())) == 2 else float("nan"),
        "wrong_extreme_lr_count": int(np.sum(((y == 1) & (log10_lr < -2)) | ((y == 0) & (log10_lr > 2)))),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--score-matrix", action="append", required=True)
    parser.add_argument("--out-dir", default="/home/bfl-pcf/VA Suite/outputs/lr_calibration/reports")
    parser.add_argument("--name", default="evaluation")
    parser.add_argument("--purpose", action="append", default=[])
    parser.add_argument("--include-dataset", action="append", default=[])
    parser.add_argument("--exclude-dataset", action="append", default=[])
    parser.add_argument("--include-generator", action="append", default=[])
    parser.add_argument("--exclude-generator", action="append", default=[])
    args = parser.parse_args()

    artifact = joblib.load(args.model)
    pipeline = artifact["pipeline"]
    feature_cols = artifact["feature_cols"]
    df = _load(args.score_matrix)
    df = df[df.get("error", "").fillna("") == ""].copy()
    if args.purpose:
        df = df[df["purpose"].isin(args.purpose)].copy()
    if args.include_dataset:
        df = df[df["dataset"].isin(args.include_dataset)].copy()
    if args.exclude_dataset:
        df = df[~df["dataset"].isin(args.exclude_dataset)].copy()
    if args.include_generator:
        df = df[df["generator"].isin(args.include_generator)].copy()
    if args.exclude_generator:
        df = df[~df["generator"].isin(args.exclude_generator)].copy()
    if df.empty:
        raise RuntimeError("No rows to evaluate")

    x = _features(df, feature_cols)
    prob = pipeline.predict_proba(x)[:, 1]
    logit = np.log(np.clip(prob, 1e-12, 1 - 1e-12) / np.clip(1 - prob, 1e-12, 1))
    df["lr_fake_probability"] = prob
    df["ln_lr"] = logit
    df["log10_lr"] = logit / math.log(10.0)
    df["lr"] = np.power(10.0, df["log10_lr"].clip(-12, 12))

    out_dir = Path(args.out_dir)
    plot_dir = out_dir.parent / "plots"
    out_dir.mkdir(parents=True, exist_ok=True)
    scored_path = out_dir / f"{args.name}_scored.csv"
    df.to_csv(scored_path, index=False)

    report: dict[str, object] = {
        "name": args.name,
        "model": args.model,
        "score_matrices": args.score_matrix,
        "scored_csv": str(scored_path),
        "overall": _metrics(df),
        "by_dataset": {},
        "by_generator": {},
    }
    for dataset, group in df.groupby("dataset"):
        report["by_dataset"][dataset] = _metrics(group)
        y = group["y_fake"].astype(int).to_numpy()
        llr = group["log10_lr"].to_numpy()
        _plot_tippett(plot_dir / f"{args.name}_{dataset}_tippett.png", llr, y, f"{args.name} Tippett {dataset}")
        _plot_hist(plot_dir / f"{args.name}_{dataset}_llr_hist.png", llr, y, f"{args.name} LLR {dataset}")
    for generator, group in df.groupby("generator"):
        report["by_generator"][generator] = _metrics(group)

    report_path = out_dir / f"{args.name}_report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
