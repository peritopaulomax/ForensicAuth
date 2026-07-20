#!/usr/bin/env python3
"""Train meta-classifier, calibrate bi-Gaussian LR, and evaluate all POC systems."""

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
import yaml
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

import lib.bootstrap  # noqa: F401
from audio_lr_dataset_utils import DETECTORS, write_json
from core.synthetic_lr_reference import (
    _apply,
    _classifier_decision_scores,
    _fit_bigauss,
    _plot_distribution,
    _plot_tippett,
    _score_dataframe,
)
from lib.features import build_system_features, feature_columns
from lib.metrics_ext import evaluate_by_dataset, evaluate_lr_frame
from lib.typicality import TypicalityReference, build_typicality_reference


def load_poc_config(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def split_name(purpose: str) -> str:
    mapping = {
        "calibration_train": "train",
        "calibration_bigauss": "val",
        "evaluation": "test",
    }
    return mapping.get(purpose, purpose)


def purpose_to_reference_split(purpose: str) -> str:
    mapping = {
        "train": "train_logreg",
        "val": "calibration_bigauss",
        "test": "test_bigauss",
    }
    return mapping[purpose]


def load_embeddings_row(row: pd.Series) -> dict[str, np.ndarray]:
    out: dict[str, np.ndarray] = {}
    for detector in DETECTORS:
        out[detector] = np.load(str(row[f"{detector}_embedding_path"]))
    return out


def load_refs_for_config(train_df: pd.DataFrame, distance: str, k: int) -> dict[str, TypicalityReference]:
    refs: dict[str, TypicalityReference] = {}
    for detector in DETECTORS:
        real_df = train_df[train_df["y_spoof"].eq(0)]
        spoof_df = train_df[train_df["y_spoof"].eq(1)]
        real_emb = np.stack([np.load(str(r[f"{detector}_embedding_path"])) for _, r in real_df.iterrows()])
        spoof_emb = np.stack([np.load(str(r[f"{detector}_embedding_path"])) for _, r in spoof_df.iterrows()])
        refs[detector] = build_typicality_reference(
            detector=detector,
            distance=distance,
            k=k,
            real_embeddings=real_emb,
            synthetic_embeddings=spoof_emb,
            real_ids=[str(r["sample_id"]) for _, r in real_df.iterrows()],
            synthetic_ids=[str(r["sample_id"]) for _, r in spoof_df.iterrows()],
        )
    return refs


def build_feature_frame(df: pd.DataFrame, refs: dict[str, TypicalityReference], system: str, eps: float) -> pd.DataFrame:
    rows: list[dict[str, float]] = []
    for _, row in df.iterrows():
        embeddings = load_embeddings_row(row)
        exclude_self = row["split"] == "train"
        rows.append(
            build_system_features(
                row,
                system=system,
                refs=refs,
                embeddings=embeddings,
                eps=eps,
                exclude_self=exclude_self,
            )
        )
    feat_df = pd.DataFrame(rows)
    out = df.copy().reset_index(drop=True)
    for col in feat_df.columns:
        out[col] = feat_df[col].values
    return out


def plot_metric_bar(results: pd.DataFrame, metric: str, out_path: Path, title: str) -> None:
    pivot = results.groupby(["system", "distance", "k"], as_index=False)[metric].mean()
    labels = [f"{row.system}/{row.distance}/k{row.k}" for row in pivot.itertuples()]
    plt.figure(figsize=(12, 5))
    plt.bar(labels, pivot[metric].values)
    plt.xticks(rotation=90)
    plt.title(title)
    plt.tight_layout()
    plt.savefig(out_path, dpi=140)
    plt.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="experiments/poc_latent_typicality/config/poc_typicality.yaml")
    parser.add_argument("--representations", default="")
    parser.add_argument("--out-dir", default="")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[2]
    poc = load_poc_config(project_root / args.config)
    rep_path = Path(args.representations) if args.representations else project_root / poc["output_root"] / "representations/representations.csv"
    out_dir = Path(args.out_dir) if args.out_dir else project_root / poc["output_root"] / "results"
    plots_dir = out_dir / "plots"
    models_dir = out_dir / "models"
    plots_dir.mkdir(parents=True, exist_ok=True)
    models_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(rep_path, low_memory=False)
    df = df[df["error"].fillna("").eq("")].copy()
    df["split"] = df["purpose"].map(split_name)
    df["y_fake"] = df["y_spoof"].astype(int)
    for detector in DETECTORS:
        df[f"{detector}_bonafide_logit"] = pd.to_numeric(df[f"{detector}_bonafide_logit"], errors="coerce")

    train_df = df[df["split"].eq("train")].copy()
    val_df = df[df["split"].eq("val")].copy()
    test_df = df[df["split"].eq("test")].copy()
    eps = float(poc.get("typicality_eps", 1e-8))
    seed = int(poc.get("random_seed", 42))

    experiment_plan = [("A", None, None)]
    for distance in poc.get("distance_metrics", ["cosine", "euclidean"]):
        for k in poc.get("k_values", [5, 10, 20, 30, 50]):
            experiment_plan.append(("B", distance, k))
    best_b: tuple[str, int, float] | None = None
    interim: list[dict[str, Any]] = []

    def run_one(system: str, distance: str | None, k: int | None) -> dict[str, Any]:
        if system == "A":
            refs = load_refs_for_config(train_df, "cosine", 10)
            feature_df = build_feature_frame(df, refs, "A", eps)
        else:
            assert distance is not None and k is not None
            refs = load_refs_for_config(train_df, distance, k)
            feature_df = build_feature_frame(df, refs, system, eps)

        cols = feature_columns(system)
        train = feature_df[feature_df["split"].eq("train")]
        x_train = train[cols].to_numpy(dtype=float)
        y_train = (1 - train["y_fake"].astype(int)).to_numpy()

        model = Pipeline(
            [
                ("scaler", StandardScaler()),
                (
                    "clf",
                    LogisticRegression(
                        penalty="l2",
                        solver="lbfgs",
                        max_iter=5000,
                        class_weight=None,
                        random_state=seed,
                    ),
                ),
            ]
        )
        model.fit(x_train, y_train)

        working = feature_df.copy()
        working["reference_split"] = working["split"].map(purpose_to_reference_split)
        calibration = _fit_bigauss(working, model, cols)
        scored = _score_dataframe(working, model, calibration, cols)

        val_scored = scored[scored["reference_split"].eq("calibration_bigauss")].copy()
        test_scored = scored[scored["reference_split"].eq("test_bigauss")].copy()
        val_metrics = evaluate_lr_frame(val_scored)
        test_metrics = evaluate_lr_frame(test_scored)
        by_dataset = evaluate_by_dataset(test_scored)

        tag = f"{system}_{distance or 'na'}_k{k or 'na'}"
        joblib.dump(
            {
                "model": model,
                "calibration": {
                    key: value
                    for key, value in calibration.items()
                    if key not in {"empirical_cdf", "inv_cdf"}
                },
                "feature_cols": cols,
                "system": system,
                "distance": distance,
                "k": k,
            },
            models_dir / f"{tag}.joblib",
        )
        _plot_tippett(plots_dir / f"tippett_{tag}.png", test_scored, f"Tippett — {tag}")
        _plot_distribution(plots_dir / f"hist_logLR_{tag}.png", test_scored, f"Distribuição LR — {tag}")
        by_dataset.to_csv(out_dir / f"metrics_by_dataset_{tag}.csv", index=False)

        row = {
            "system": system,
            "distance": distance or "",
            "k": k if k is not None else "",
            "val_cllr": val_metrics["cllr"],
            "val_min_cllr": val_metrics["min_cllr"],
            "test_cllr": test_metrics["cllr"],
            "test_min_cllr": test_metrics["min_cllr"],
            "test_auc": test_metrics["auc"],
            "test_eer": test_metrics["eer"],
            **{f"test_{key}": value for key, value in test_metrics.items() if key.startswith("err_")},
        }
        return row

    results: list[dict[str, Any]] = []
    for system, distance, k in experiment_plan:
        print(f"Running system={system} distance={distance} k={k}", flush=True)
        row = run_one(system, distance, k)
        results.append(row)
        if system == "B":
            interim.append(row)

    interim_df = pd.DataFrame(interim)
    best_rows = interim_df.sort_values(["val_cllr", "val_min_cllr"]).head(2)
    for _, best in best_rows.iterrows():
        for system in ("C", "D"):
            print(f"Running system={system} distance={best['distance']} k={best['k']}", flush=True)
            results.append(run_one(system, str(best["distance"]), int(best["k"])))

    results_df = pd.DataFrame(results)
    results_df.to_csv(out_dir / "poc_results.csv", index=False)
    plot_metric_bar(results_df, "test_cllr", plots_dir / "cllr_by_system.png", "Cllr teste por sistema")
    dataset_means = []
    for _, row in results_df.iterrows():
        tag = f"{row['system']}_{row['distance'] or 'na'}_k{row['k'] or 'na'}"
        path = out_dir / f"metrics_by_dataset_{tag}.csv"
        if path.exists():
            part = pd.read_csv(path)
            part["system"] = row["system"]
            part["distance"] = row["distance"]
            part["k"] = row["k"]
            dataset_means.append(part)
    if dataset_means:
        ds_df = pd.concat(dataset_means, ignore_index=True)
        ds_pivot = ds_df.groupby(["system", "dataset"], as_index=False)["cllr"].mean()
        plt.figure(figsize=(10, 5))
        for system, group in ds_pivot.groupby("system"):
            plt.plot(group["dataset"], group["cllr"], marker="o", label=system)
        plt.xticks(rotation=30, ha="right")
        plt.ylabel("Cllr")
        plt.title("Cllr por dataset")
        plt.legend()
        plt.tight_layout()
        plt.savefig(plots_dir / "cllr_by_dataset.png", dpi=140)
        plt.close()

    best = results_df.sort_values(["test_cllr", "test_min_cllr"]).iloc[0].to_dict()
    write_json(out_dir / "best_config.json", best)
    print(json.dumps({"best": best, "results_csv": str(out_dir / 'poc_results.csv')}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
