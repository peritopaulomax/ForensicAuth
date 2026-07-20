#!/usr/bin/env python3
"""Extract detector scores and penultimate-layer embeddings for image LR typicality.

Optimized version: processes one detector at a time to keep GPU memory bounded,
uses direct embedding extractors (avoiding pipeline overhead), and resumes
per-detector progress.

Reads the augmented score matrix (originals + augmentations), runs each image
through the selected detectors, and writes one ``.npy`` file per detector per
sample plus a ``representations.csv`` linking scores and embedding paths.
"""

from __future__ import annotations

import argparse
import csv
import gc
import json
import math
import sys
import time
from pathlib import Path
from typing import Any, Callable

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
    release_gpu_memory,
)
from core.legacy.truebees_clip_d.clipd_pipeline import clear_clipd_model_cache

DETECTORS = list(DEFAULT_SYNTHETIC_ANALYSES)
HF_DETECTORS = ("ai_image_detector_deploy", "sdxl_flux_detector_v1_1")
LEGACY_DETECTORS = ("bfree", "corvi2023", "safe")


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
    """Release model-specific GPU memory for legacy detectors."""
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
    """Load a single HuggingFace base detector and its processor."""
    model_id = "model_1" if detector == "ai_image_detector_deploy" else "model_4"
    local_path = _hf_local_path(MODEL_PATHS[model_id])
    processor = AutoImageProcessor.from_pretrained(local_path, local_files_only=True)
    model = AutoModelForImageClassification.from_pretrained(
        local_path,
        local_files_only=True,
    ).to(device)
    model.eval()
    return model, processor


def _sample_has_embedding(row: dict[str, Any], detector: str, embed_dir: Path) -> bool:
    path_col = f"{detector}_embedding_path"
    existing_path = row.get(path_col)
    if existing_path and Path(existing_path).is_file():
        return True
    sid = row.get("sample_id")
    if sid and (embed_dir / f"{sid}__{detector}.npy").is_file():
        return True
    return False


def _extract_for_detector(
    detector: str,
    records: list[dict[str, Any]],
    output_rows: dict[str, dict[str, Any]],
    embed_dir: Path,
    device: torch.device,
    flush_every: int = 25,
    write_csv: Callable[[], None] | None = None,
) -> dict[str, Any]:
    """Extract embeddings for ``detector`` across all records.

    Updates ``output_rows`` in place and returns per-detector timing stats.
    """
    model: Any = None
    processor: Any = None
    if detector in HF_DETECTORS:
        print(f"Loading {detector} model on {device}...", flush=True)
        model, processor = _load_hf_detector(detector, device)

    extractor = EMBEDDING_EXTRACTORS[detector]

    times: list[float] = []
    processed = 0
    skipped = 0
    errors = 0
    start_detector = time.time()

    total = len(records)
    for idx, record in enumerate(records, start=1):
        sample_id = record["sample_id"]
        out_row = output_rows.setdefault(sample_id, dict(record))

        if _sample_has_embedding(out_row, detector, embed_dir):
            path_col = f"{detector}_embedding_path"
            if not out_row.get(path_col):
                sid = out_row.get("sample_id")
                if sid:
                    emb_path = embed_dir / f"{sid}__{detector}.npy"
                    if emb_path.is_file():
                        out_row[path_col] = str(emb_path)
                        out_row[f"{detector}_embedding_dim"] = int(np.load(emb_path).size)
            skipped += 1
            continue

        image_path = Path(out_row["image_path"])
        if not image_path.is_absolute():
            image_path = ROOT / image_path

        if not image_path.exists():
            out_row["error"] = f"FileNotFoundError: {image_path}"
            errors += 1
            continue

        t0 = time.time()
        try:
            image = Image.open(image_path).convert("RGB")
            if detector == "ai_image_detector_deploy":
                emb = extract_ai_image_detector_embedding(image, model, processor)
            elif detector == "sdxl_flux_detector_v1_1":
                emb = extract_sdxl_flux_embedding(image, model, processor)
            else:
                emb = extractor(image, device=device)

            emb_path = embed_dir / f"{sample_id}__{detector}.npy"
            np.save(emb_path, np.asarray(emb, dtype=np.float32))
            out_row[f"{detector}_embedding_path"] = str(emb_path)
            out_row[f"{detector}_embedding_dim"] = int(emb.size)
            processed += 1
            times.append(time.time() - t0)
        except Exception as exc:
            out_row["error"] = f"{detector}: {repr(exc)}"
            errors += 1

        if idx % flush_every == 0:
            if write_csv is not None:
                write_csv()
            print(
                f"[{detector}] {idx}/{total} processed={processed} skipped={skipped} errors={errors} "
                f"last={times[-1]:.2f}s mean={sum(times[-max(10,len(times))::]) / min(10, len(times)):.2f}s",
                flush=True,
            )

    elapsed = time.time() - start_detector
    _clear_detector_cache(detector)
    if model is not None:
        del model, processor
    _clear_detector_cache(detector)

    return {
        "detector": detector,
        "processed": processed,
        "skipped": skipped,
        "errors": errors,
        "elapsed_seconds": elapsed,
        "mean_per_sample_seconds": float(np.mean(times)) if times else 0.0,
        "median_per_sample_seconds": float(np.median(times)) if times else 0.0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--score-matrix",
        default="outputs/lr_calibration/score_matrices/lr_scores_balanced_full_augmented.csv",
        help="Path to the augmented score matrix CSV.",
    )
    parser.add_argument(
        "--out-dir",
        default="outputs/lr_calibration/synthetic_image/representations",
        help="Output directory for representations.csv and embeddings/.",
    )
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--selected-analyses",
        nargs="+",
        choices=DETECTORS,
        default=DETECTORS,
        help="Detectors to extract embeddings for.",
    )
    parser.add_argument(
        "--device",
        default="cuda" if torch.cuda.is_available() else "cpu",
        help="Torch device for legacy detectors.",
    )
    parser.add_argument(
        "--flush-every",
        type=int,
        default=25,
        help="Write CSV progress every N samples.",
    )
    args = parser.parse_args()

    score_matrix_path = ROOT / args.score_matrix
    out_dir = ROOT / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    embed_dir = out_dir / "embeddings"
    embed_dir.mkdir(parents=True, exist_ok=True)
    meta_path = out_dir / "representations.csv"
    timing_path = out_dir / "extract_timing.json"

    selected = list(args.selected_analyses)
    device = torch.device(args.device)

    df = pd.read_csv(score_matrix_path, low_memory=False)
    if "error" in df.columns:
        df = df[df["error"].fillna("").eq("")].copy()

    records = df.to_dict(orient="records")
    if args.limit > 0:
        records = records[: args.limit]

    output_rows: dict[str, dict[str, Any]] = {}

    # Resume: read existing CSV and reconstruct rows by sample_id.
    if args.resume and meta_path.exists():
        with meta_path.open(encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                sid = str(row.get("sample_id") or "")
                if sid:
                    output_rows[sid] = row
        print(f"Resumed {len(output_rows)} rows from {meta_path}", flush=True)

    # Build records with normalized sample_id and pre-computed scores.
    normalized_records: list[dict[str, Any]] = []
    for record_idx, record in enumerate(records):
        dataset = str(record.get("dataset", ""))
        generator = str(record.get("generator", ""))
        raw_source_id = record.get("source_id")
        # source_id may be NaN/empty in the score matrix; fall back to a stable
        # row index to avoid sample_id collisions across rows.
        if raw_source_id is None or (isinstance(raw_source_id, float) and pd.isna(raw_source_id)) or str(raw_source_id).strip() in ("", "nan"):
            source_id = f"row_idx_{record_idx}"
        else:
            source_id = source_id_stem(str(raw_source_id))
        raw_aug = record.get("augmentation", "")
        augmentation = "" if pd.isna(raw_aug) else str(raw_aug).strip()
        sample_id = build_sample_id(
            dataset=dataset,
            generator=generator,
            source_id=source_id,
            augmentation=augmentation,
        )

        image_path = Path(str(record.get("image_path", "")))
        if not image_path.is_absolute():
            image_path = ROOT / image_path

        out_row = output_rows.get(sample_id, {
            "sample_id": sample_id,
            "dataset": dataset,
            "generator": generator,
            "purpose": str(record.get("purpose", "reference_population")),
            "label": str(record.get("label", "")),
            "y_fake": int(record.get("y_fake", 0)),
            "source_id": source_id,
            "image_path": str(image_path),
            "augmentation": augmentation or ORIGINAL_AUGMENTATION_TAG,
            "error": "",
        })

        # Copy pre-computed scores from the matrix when available.
        for detector in DETECTORS:
            fake_col, real_col, raw_col, decision_col = _score_columns(detector)
            if fake_col in record and _is_finite(record[fake_col]):
                out_row[fake_col] = float(record[fake_col])
            if real_col in record and _is_finite(record[real_col]):
                out_row[real_col] = float(record[real_col])
            if raw_col in record:
                out_row[raw_col] = record[raw_col]
            if decision_col in record:
                out_row[decision_col] = record[decision_col]

        output_rows[sample_id] = out_row
        normalized_records.append(out_row)

    def _write_csv() -> None:
        rows = list(output_rows.values())
        fieldnames = sorted({key for r in rows for key in r})
        with meta_path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    _write_csv()

    detector_stats: list[dict[str, Any]] = []
    for detector in selected:
        print(f"\n=== Extracting embeddings for detector: {detector} ===", flush=True)
        stats = _extract_for_detector(
            detector=detector,
            records=normalized_records,
            output_rows=output_rows,
            embed_dir=embed_dir,
            device=device,
            flush_every=args.flush_every,
            write_csv=_write_csv,
        )
        detector_stats.append(stats)
        _write_csv()
        timing_path.write_text(json.dumps({"detectors": detector_stats}, indent=2), encoding="utf-8")
        print(json.dumps(stats, indent=2), flush=True)

    _write_csv()

    summary = {
        "score_matrix": str(score_matrix_path),
        "representations_csv": str(meta_path),
        "rows": len(output_rows),
        "errors": sum(1 for row in output_rows.values() if row.get("error")),
        "embeddings_dir": str(embed_dir),
        "selected_analyses": selected,
        "device": str(device),
        "detector_stats": detector_stats,
    }
    (out_dir / "extract_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
