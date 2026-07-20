#!/usr/bin/env python3
"""Build k-NN reference banks and radius distributions from train split."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

import lib.bootstrap  # noqa: F401
from audio_lr_dataset_utils import DETECTORS
from lib.typicality import build_typicality_reference, save_typicality_reference


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


def load_embeddings(df: pd.DataFrame, detector: str) -> tuple[np.ndarray, list[str]]:
    embeddings: list[np.ndarray] = []
    ids: list[str] = []
    path_col = f"{detector}_embedding_path"
    for _, row in df.iterrows():
        emb_path = Path(str(row[path_col]))
        embeddings.append(np.load(emb_path))
        ids.append(str(row["sample_id"]))
    return np.stack(embeddings, axis=0), ids


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="experiments/poc_latent_typicality/config/poc_typicality.yaml")
    parser.add_argument("--representations", default="")
    parser.add_argument("--out-dir", default="")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[2]
    poc = load_poc_config(project_root / args.config)
    rep_path = Path(args.representations) if args.representations else project_root / poc["output_root"] / "representations/representations.csv"
    out_root = Path(args.out_dir) if args.out_dir else project_root / poc["output_root"] / "knn"

    df = pd.read_csv(rep_path, low_memory=False)
    df = df[df["error"].fillna("").eq("")].copy()
    df["split"] = df["purpose"].map(split_name)
    train = df[df["split"].eq("train")].copy()

    summary: dict[str, Any] = {"references": []}
    for distance in poc.get("distance_metrics", ["cosine", "euclidean"]):
        for k in poc.get("k_values", [5, 10, 20, 30, 50]):
            ref_dir = out_root / f"{distance}_k{k}"
            ref_dir.mkdir(parents=True, exist_ok=True)
            for detector in DETECTORS:
                real_df = train[train["y_spoof"].eq(0)]
                spoof_df = train[train["y_spoof"].eq(1)]
                real_emb, real_ids = load_embeddings(real_df, detector)
                spoof_emb, spoof_ids = load_embeddings(spoof_df, detector)
                ref = build_typicality_reference(
                    detector=detector,
                    distance=distance,
                    k=int(k),
                    real_embeddings=real_emb,
                    synthetic_embeddings=spoof_emb,
                    real_ids=real_ids,
                    synthetic_ids=spoof_ids,
                )
                save_typicality_reference(ref, ref_dir)
            summary["references"].append({"distance": distance, "k": k, "dir": str(ref_dir)})

    (out_root / "knn_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
