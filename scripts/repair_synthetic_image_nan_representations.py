#!/usr/bin/env python3
"""Repair representations rows whose source_id was NaN in the score matrix.

The initial extraction converted NaN source_ids to the literal string "nan",
causing sample_id collisions and missing embeddings for ~8k valid images.
This script re-extracts embeddings for those rows using a stable row-index
sample_id and rewrites the representations CSV.
"""

from __future__ import annotations

import csv
import gc
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch
from PIL import Image
from transformers import AutoImageProcessor, AutoModelForImageClassification

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src" / "backend"))

from core.latent_typicality.representations_utils import (
    ORIGINAL_AUGMENTATION_TAG,
    build_sample_id,
    source_id_stem,
)
from core.legacy.bfree.bfree_pipeline import clear_bfree_model_cache
from core.legacy.safe.safe_pipeline import clear_safe_model_cache
from core.legacy.synthetic_image_detection.embedding_utils import (
    EMBEDDING_EXTRACTORS,
    extract_ai_image_detector_embedding,
    extract_sdxl_flux_embedding,
)
from core.legacy.synthetic_image_detection.pipeline import (
    DEFAULT_SYNTHETIC_ANALYSES,
    MODEL_PATHS,
    _hf_local_path,
)
from core.legacy.truebees_clip_d.clipd_pipeline import clear_clipd_model_cache

DETECTORS = list(DEFAULT_SYNTHETIC_ANALYSES)
HF_DETECTORS = ("ai_image_detector_deploy", "sdxl_flux_detector_v1_1")


def _is_finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _score_columns(detector: str) -> tuple[str, str, str, str]:
    return (
        f"{detector}_fake_prob",
        f"{detector}_real_prob",
        f"{detector}_raw_score",
        f"{detector}_decision",
    )


def _clear_detector_cache(detector: str) -> None:
    if detector == "bfree":
        clear_bfree_model_cache()
    elif detector in ("corvi2023", "clipd"):
        clear_clipd_model_cache()
    elif detector == "safe":
        clear_safe_model_cache()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    gc.collect()


def _load_hf_detector(detector: str, device: torch.device) -> tuple[Any, Any]:
    model_id = "model_1" if detector == "ai_image_detector_deploy" else "model_4"
    local_path = _hf_local_path(MODEL_PATHS[model_id])
    processor = AutoImageProcessor.from_pretrained(local_path, local_files_only=True)
    model = AutoModelForImageClassification.from_pretrained(
        local_path,
        local_files_only=True,
    ).to(device)
    model.eval()
    return model, processor


def main() -> None:
    score_matrix_path = ROOT / "outputs/lr_calibration/score_matrices/lr_scores_balanced_full_augmented.csv"
    out_dir = ROOT / "outputs/lr_calibration/synthetic_image/representations"
    embed_dir = out_dir / "embeddings"
    meta_path = out_dir / "representations.csv"
    log_path = out_dir / "repair_nan.log"

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    df = pd.read_csv(score_matrix_path, low_memory=False)
    if "error" in df.columns:
        df = df[df["error"].fillna("").eq("")].copy()

    # Identify rows with NaN/empty source_id and existing image files.
    nan_rows: list[tuple[int, pd.Series]] = []
    for idx, row in df.iterrows():
        source_id = row.get("source_id")
        is_nan = (
            source_id is None
            or (isinstance(source_id, float) and pd.isna(source_id))
            or str(source_id).strip() in ("", "nan")
        )
        if not is_nan:
            continue
        image_path = Path(str(row.get("image_path", "")))
        if not image_path.is_absolute():
            image_path = ROOT / image_path
        if image_path.exists():
            nan_rows.append((int(idx), row))

    total = len(nan_rows)
    print(f"Found {total} NaN-source_id rows with existing images to repair.")

    # Load existing CSV rows, dropping old __nan__ rows.
    existing_rows: list[dict[str, Any]] = []
    if meta_path.exists():
        with meta_path.open(encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                if "__nan__" in str(row.get("sample_id", "")):
                    continue
                existing_rows.append(row)
        print(f"Kept {len(existing_rows)} non-NaN rows from existing CSV.")

    # Prepare new rows with row-index sample_ids.
    new_rows: list[dict[str, Any]] = []
    for idx, row in nan_rows:
        dataset = str(row.get("dataset", ""))
        generator = str(row.get("generator", ""))
        source_id = f"row_idx_{idx}"
        raw_aug = row.get("augmentation", "")
        augmentation = "" if pd.isna(raw_aug) else str(raw_aug).strip()
        sample_id = build_sample_id(
            dataset=dataset,
            generator=generator,
            source_id=source_id,
            augmentation=augmentation,
        )
        image_path = Path(str(row.get("image_path", "")))
        if not image_path.is_absolute():
            image_path = ROOT / image_path

        out_row: dict[str, Any] = {
            "sample_id": sample_id,
            "dataset": dataset,
            "generator": generator,
            "purpose": str(row.get("purpose", "reference_population")),
            "label": str(row.get("label", "")),
            "y_fake": int(row.get("y_fake", 0)),
            "source_id": source_id,
            "image_path": str(image_path),
            "augmentation": augmentation or ORIGINAL_AUGMENTATION_TAG,
            "error": "",
        }
        for detector in DETECTORS:
            fake_col, real_col, raw_col, decision_col = _score_columns(detector)
            if fake_col in row.index and _is_finite(row[fake_col]):
                out_row[fake_col] = float(row[fake_col])
            if real_col in row.index and _is_finite(row[real_col]):
                out_row[real_col] = float(row[real_col])
            if raw_col in row.index:
                out_row[raw_col] = row[raw_col]
            if decision_col in row.index:
                out_row[decision_col] = row[decision_col]
        new_rows.append(out_row)

    def _write_csv(rows: list[dict[str, Any]]) -> None:
        fieldnames = sorted({key for r in rows for key in r})
        with meta_path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def log(msg: str) -> None:
        print(msg, flush=True)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(msg + "\n")

    # Process one detector at a time.
    detector_stats: list[dict[str, Any]] = []
    for detector in DETECTORS:
        log(f"\n=== Repairing detector: {detector} ({total} rows) ===")
        model: Any = None
        processor: Any = None
        if detector in HF_DETECTORS:
            log(f"Loading {detector} model on {device}...")
            model, processor = _load_hf_detector(detector, device)
        extractor = EMBEDDING_EXTRACTORS[detector]

        processed = 0
        errors = 0
        times: list[float] = []
        t0_detector = time.time()

        for i, out_row in enumerate(new_rows, start=1):
            sample_id = out_row["sample_id"]
            emb_path = embed_dir / f"{sample_id}__{detector}.npy"
            if emb_path.is_file():
                # Reuse if already present from a previous repair attempt.
                out_row[f"{detector}_embedding_path"] = str(emb_path)
                continue

            image_path = Path(out_row["image_path"])
            t0 = time.time()
            try:
                image = Image.open(image_path).convert("RGB")
                if detector == "ai_image_detector_deploy":
                    emb = extract_ai_image_detector_embedding(image, model, processor)
                elif detector == "sdxl_flux_detector_v1_1":
                    emb = extract_sdxl_flux_embedding(image, model, processor)
                else:
                    emb = extractor(image, device=device)
                np.save(emb_path, np.asarray(emb, dtype=np.float32))
                out_row[f"{detector}_embedding_path"] = str(emb_path)
                out_row[f"{detector}_embedding_dim"] = int(emb.size)
                processed += 1
                times.append(time.time() - t0)
            except Exception as exc:
                out_row["error"] = f"{detector}: {repr(exc)}"
                errors += 1

            if i % 50 == 0:
                _write_csv(existing_rows + new_rows)
                mean_recent = sum(times[-10:]) / min(10, len(times)) if times else 0.0
                log(
                    f"[{detector}] {i}/{total} processed={processed} errors={errors} "
                    f"last={times[-1]:.2f}s mean_recent={mean_recent:.2f}s"
                )

        _clear_detector_cache(detector)
        if model is not None:
            del model, processor
        _clear_detector_cache(detector)

        elapsed = time.time() - t0_detector
        stats = {
            "detector": detector,
            "processed": processed,
            "errors": errors,
            "elapsed_seconds": elapsed,
            "mean_per_sample_seconds": float(np.mean(times)) if times else 0.0,
        }
        detector_stats.append(stats)
        log(json.dumps(stats, indent=2))

    # Final CSV write.
    all_rows = existing_rows + new_rows
    _write_csv(all_rows)

    summary = {
        "repaired_nan_rows": total,
        "final_rows": len(all_rows),
        "detector_stats": detector_stats,
    }
    (out_dir / "repair_nan_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    log(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
