#!/usr/bin/env python3
"""Inventory LR typicality assets per dataset/generator subgroup.

Target per subgroup (reference population):
  - 500 bonafide + 500 spoof originals (scores in score matrix)
  - 4 augmentations each (mp3_128k, opus_32k, noise_snr_20, noise_snr_15)
  - scores + embeddings (3 detectors) for typicality calibration

Outputs CSV + JSON summary under outputs/lr_calibration/audio_spoofing/inventory/
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src" / "backend"))

from audio_lr_dataset_utils import DETECTORS
from core.latent_typicality.representations_utils import (
    ORIGINAL_AUGMENTATION_TAG,
    build_sample_id,
    resolve_parent_source_id,
)

AUGMENTATIONS = ("mp3_128k", "opus_32k", "noise_snr_20", "noise_snr_15")
TARGET_PER_CLASS = 500
LABELS = ("bonafide", "spoof")


def load_config(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _has_scores(row: pd.Series) -> bool:
    for det in DETECTORS:
        val = row.get(f"{det}_bonafide_logit")
        if val is None or (isinstance(val, float) and pd.isna(val)) or val == "":
            return False
    return True


def _has_embeddings(row: pd.Series) -> bool:
    for det in DETECTORS:
        path = row.get(f"{det}_embedding_path")
        if path is None or (isinstance(path, float) and pd.isna(path)) or not Path(str(path)).is_file():
            return False
    return True


def _sample_id_from_manifest_row(row: dict[str, Any] | pd.Series, augmentation: str = "") -> str:
    aug = augmentation or str(row.get("augmentation") or "") or ORIGINAL_AUGMENTATION_TAG
    return build_sample_id(
        dataset=str(row.get("dataset", "")),
        generator=str(row.get("generator", "")),
        source_id=resolve_parent_source_id(row),
        augmentation=aug,
    )


def _load_representations_index(path: Path) -> dict[str, dict[str, Any]]:
    if not path.is_file():
        return {}
    df = pd.read_csv(path, low_memory=False)
    if "error" in df.columns:
        df = df[df["error"].fillna("").eq("")].copy()
    index: dict[str, dict[str, Any]] = {}
    for record in df.to_dict(orient="records"):
        sid = str(record.get("sample_id") or "")
        if sid:
            index[sid] = record
    return index


def _count_orig_scores(score_df: pd.DataFrame, dataset: str, generator: str, label: str) -> int:
    sub = score_df[
        score_df["dataset"].astype(str).eq(dataset)
        & score_df["generator"].astype(str).eq(generator)
        & score_df["label"].astype(str).eq(label)
    ]
    if "error" in sub.columns:
        sub = sub[sub["error"].fillna("").eq("")]
    return int(len(sub))


def build_inventory(
    *,
    score_matrix: Path,
    manifest: Path,
    originals_reps: Path,
    augmented_reps: Path,
    target_per_class: int = TARGET_PER_CLASS,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    score_df = pd.read_csv(score_matrix, low_memory=False)
    if "error" in score_df.columns:
        score_df = score_df[score_df["error"].fillna("").eq("")].copy()

    manifest_df = pd.read_csv(manifest, low_memory=False) if manifest.is_file() else pd.DataFrame()
    orig_index = _load_representations_index(originals_reps)
    aug_index = _load_representations_index(augmented_reps)

    subgroups = sorted(
        {(str(r["dataset"]), str(r["generator"])) for _, r in score_df[["dataset", "generator"]].drop_duplicates().iterrows()}
    )

    rows: list[dict[str, Any]] = []
    for dataset, generator in subgroups:
        row: dict[str, Any] = {
            "dataset": dataset,
            "generator": generator,
            "target_per_class": target_per_class,
        }

        total_need_emb = 0
        total_have_emb = 0
        total_need_rep = 0
        total_have_rep = 0

        for label in LABELS:
            short = "bf" if label == "bonafide" else "sp"
            orig_scores = _count_orig_scores(score_df, dataset, generator, label)
            row[f"{short}_orig_scores"] = orig_scores
            row[f"{short}_orig_target_met"] = orig_scores >= target_per_class

            orig_emb = 0
            if len(manifest_df):
                pass
            orig_rows_score = score_df[
                score_df["dataset"].astype(str).eq(dataset)
                & score_df["generator"].astype(str).eq(generator)
                & score_df["label"].astype(str).eq(label)
            ]
            for rec in orig_rows_score.to_dict(orient="records"):
                sid = build_sample_id(
                    dataset=dataset,
                    generator=generator,
                    source_id=str(rec.get("source_id", "")),
                    augmentation="",
                )
                rep = orig_index.get(sid)
                if rep and _has_embeddings(rep):
                    orig_emb += 1
            row[f"{short}_orig_embeddings"] = orig_emb

            if len(manifest_df):
                wav_orig = manifest_df[
                    manifest_df["dataset"].astype(str).eq(dataset)
                    & manifest_df["generator"].astype(str).eq(generator)
                    & manifest_df["label"].astype(str).eq(label)
                    & manifest_df["augmentation"].fillna("").astype(str).eq("")
                ]
            else:
                wav_orig = pd.DataFrame()
            row[f"{short}_orig_wavs_aug_manifest"] = int(len(wav_orig)) if len(manifest_df) else orig_scores

            for aug in AUGMENTATIONS:
                if len(manifest_df):
                    wav_aug = manifest_df[
                        manifest_df["dataset"].astype(str).eq(dataset)
                        & manifest_df["generator"].astype(str).eq(generator)
                        & manifest_df["label"].astype(str).eq(label)
                        & manifest_df["augmentation"].astype(str).eq(aug)
                    ]
                    wav_n = int(len(wav_aug))
                else:
                    wav_n = 0
                row[f"{short}_{aug}_wavs"] = wav_n
                row[f"{short}_{aug}_wav_target_met"] = wav_n >= target_per_class

                emb_n = 0
                score_n = 0
                if len(manifest_df):
                    for mrec in wav_aug.to_dict(orient="records"):
                        sid = _sample_id_from_manifest_row(mrec, aug)
                        rep = aug_index.get(sid)
                        if rep:
                            if _has_scores(rep):
                                score_n += 1
                            if _has_embeddings(rep):
                                emb_n += 1
                row[f"{short}_{aug}_scores"] = score_n
                row[f"{short}_{aug}_embeddings"] = emb_n

                need = min(orig_scores, wav_n, target_per_class)
                total_need_rep += need
                total_have_rep += score_n
                total_need_emb += need
                total_have_emb += emb_n

            total_need_emb += min(orig_scores, target_per_class)
            total_have_emb += orig_emb
            total_need_rep += min(orig_scores, target_per_class)
            total_have_rep += orig_scores

        row["bonafide_aug_wavs_ok"] = all(row.get(f"bf_{a}_wav_target_met", False) for a in AUGMENTATIONS)
        row["spoof_aug_wavs_ok"] = all(row.get(f"sp_{a}_wav_target_met", False) for a in AUGMENTATIONS)
        row["bonafide_orig_ok"] = row.get("bf_orig_target_met", False) and row.get("bf_orig_embeddings", 0) >= target_per_class
        row["spoof_orig_ok"] = row.get("sp_orig_target_met", False) and row.get("sp_orig_embeddings", 0) >= target_per_class
        row["aug_embeddings_complete"] = all(
            row.get(f"{short}_{aug}_embeddings", 0) >= min(row.get(f"{short}_orig_scores", 0), target_per_class)
            for short in ("bf", "sp")
            for aug in AUGMENTATIONS
        )
        row["fully_ready_typicality"] = (
            row["bonafide_orig_ok"]
            and row["spoof_orig_ok"]
            and row["bonafide_aug_wavs_ok"]
            and row["spoof_aug_wavs_ok"]
            and row["aug_embeddings_complete"]
        )
        row["rep_rows_needed_estimate"] = total_need_rep
        row["rep_rows_have_scores_emb"] = total_have_emb
        row["rep_completion_pct"] = round(100.0 * total_have_emb / total_need_rep, 1) if total_need_rep else 0.0
        rows.append(row)

    df = pd.DataFrame(rows)
    summary = {
        "target_per_class": target_per_class,
        "augmentations": list(AUGMENTATIONS),
        "subgroups_total": int(len(df)),
        "subgroups_fully_ready": int(df["fully_ready_typicality"].sum()) if len(df) else 0,
        "subgroups_partial": int((~df["fully_ready_typicality"] & (df["rep_completion_pct"] > 0)).sum()) if len(df) else 0,
        "subgroups_empty_rep": int((df["rep_completion_pct"] == 0).sum()) if len(df) else 0,
        "score_matrix_rows": int(len(score_df)),
        "manifest_rows": int(len(manifest_df)),
        "originals_rep_rows": len(orig_index),
        "augmented_rep_rows": len(aug_index),
    }
    return df, summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/audio_spoofing_typicality.yaml")
    parser.add_argument(
        "--out-dir",
        default="outputs/lr_calibration/audio_spoofing/inventory",
    )
    args = parser.parse_args()

    cfg = load_config(ROOT / args.config)
    out_dir = ROOT / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    score_matrix = ROOT / cfg.get("score_matrix_base", "outputs/lr_calibration/audio_spoofing/score_matrices/lr_scores_balanced_full.csv")
    manifest = ROOT / cfg.get("augmented_manifest", "outputs/lr_calibration/audio_spoofing/samples/augmented/manifest.csv")
    originals_reps = ROOT / cfg.get("originals_embeddings_dir", "outputs/lr_calibration/audio_spoofing/representations/originals") / "representations.csv"
    augmented_reps = ROOT / cfg.get("augmented_embeddings_dir", "outputs/lr_calibration/audio_spoofing/representations/augmented") / "representations.csv"

    df, summary = build_inventory(
        score_matrix=score_matrix,
        manifest=manifest,
        originals_reps=originals_reps,
        augmented_reps=augmented_reps,
    )

    detail_path = out_dir / "typicality_by_subgroup.csv"
    summary_path = out_dir / "typicality_summary.json"
    df.to_csv(detail_path, index=False)
    summary["detail_csv"] = str(detail_path)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"\nWrote {detail_path}")


if __name__ == "__main__":
    main()
