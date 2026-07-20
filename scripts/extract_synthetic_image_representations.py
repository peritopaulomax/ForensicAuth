#!/usr/bin/env python3
"""Extract detector scores and penultimate-layer embeddings for image LR typicality.

Reads the augmented score matrix (originals + augmentations), runs each image
through the synthetic-image detection pipeline with ``return_embedding=True``,
and writes one ``.npy`` file per detector per sample plus a
``representations.csv`` linking scores and embedding paths.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src" / "backend"))

from core.latent_typicality.representations_utils import (
    ORIGINAL_AUGMENTATION_TAG,
    build_sample_id,
    source_id_stem,
)
from core.legacy.synthetic_image_detection.pipeline import (
    DEFAULT_SYNTHETIC_ANALYSES,
    run_synthetic_image_detection_analysis,
)

DETECTORS = list(DEFAULT_SYNTHETIC_ANALYSES)


def _is_finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _embeddings_on_disk(sample_id: str, embed_dir: Path) -> bool:
    for detector in DETECTORS:
        if not (embed_dir / f"{sample_id}__{detector}.npy").is_file():
            return False
    return True


def _score_columns(detector: str) -> tuple[str, str, str, str]:
    return (
        f"{detector}_fake_prob",
        f"{detector}_real_prob",
        f"{detector}_raw_score",
        f"{detector}_decision",
    )


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
    args = parser.parse_args()

    score_matrix_path = ROOT / args.score_matrix
    out_dir = ROOT / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    embed_dir = out_dir / "embeddings"
    embed_dir.mkdir(parents=True, exist_ok=True)
    meta_path = out_dir / "representations.csv"

    selected = list(args.selected_analyses)

    df = pd.read_csv(score_matrix_path, low_memory=False)
    if "error" in df.columns:
        df = df[df["error"].fillna("").eq("")].copy()

    records = df.to_dict(orient="records")
    if args.limit > 0:
        records = records[: args.limit]

    existing: dict[str, dict[str, Any]] = {}
    if args.resume and meta_path.exists():
        with meta_path.open(encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                if row.get("error"):
                    continue
                sid = str(row.get("sample_id") or "")
                if not (sid and _embeddings_on_disk(sid, embed_dir)):
                    continue
                existing[sid] = row

    output_rows: list[dict[str, Any]] = list(existing.values())
    done_ids = set(existing)

    total = len(records)
    for idx, record in enumerate(records, start=1):
        dataset = str(record.get("dataset", ""))
        generator = str(record.get("generator", ""))
        source_id = source_id_stem(str(record.get("source_id", "")))
        raw_aug = record.get("augmentation", "")
        augmentation = "" if pd.isna(raw_aug) else str(raw_aug).strip()
        sample_id = build_sample_id(
            dataset=dataset,
            generator=generator,
            source_id=source_id,
            augmentation=augmentation,
        )

        if sample_id in done_ids:
            continue

        image_path = Path(str(record.get("image_path", "")))
        if not image_path.is_absolute():
            image_path = ROOT / image_path

        out_row: dict[str, Any] = {
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
            "elapsed_seconds": "",
        }

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

        if not image_path.exists():
            out_row["error"] = f"FileNotFoundError: {image_path}"
            output_rows.append(out_row)
            done_ids.add(sample_id)
            continue

        start = time.time()
        try:
            image = Image.open(image_path).convert("RGB")
            result = run_synthetic_image_detection_analysis(
                image,
                generate_visuals=False,
                selected_analyses=selected,
                return_embedding=True,
            )
            detector_scores = result.get("detector_scores", {})
            for detector in selected:
                scores = detector_scores.get(detector) or {}
                embedding = scores.get("embedding")
                if embedding is None:
                    raise RuntimeError(f"Embedding missing for detector {detector}")
                emb_path = embed_dir / f"{sample_id}__{detector}.npy"
                np.save(emb_path, np.asarray(embedding, dtype=np.float32))
                out_row[f"{detector}_embedding_path"] = str(emb_path)
                out_row[f"{detector}_embedding_dim"] = int(np.asarray(embedding).size)
                # Prefer freshly computed finite scores when available.
                fake_prob = scores.get("fake_prob")
                if fake_prob is not None and _is_finite(fake_prob):
                    out_row[f"{detector}_fake_prob"] = float(fake_prob)
                    out_row[f"{detector}_real_prob"] = 1.0 - float(fake_prob)
        except Exception as exc:
            out_row["error"] = repr(exc)

        out_row["elapsed_seconds"] = f"{time.time() - start:.3f}"
        output_rows.append(out_row)
        done_ids.add(sample_id)

        if idx % 25 == 0 or out_row.get("error"):
            fieldnames = sorted({key for r in output_rows for key in r})
            with meta_path.open("w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(output_rows)
            print(f"Processed {idx}/{total}", flush=True)

    fieldnames = sorted({key for r in output_rows for key in r})
    with meta_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(output_rows)

    summary = {
        "score_matrix": str(score_matrix_path),
        "representations_csv": str(meta_path),
        "rows": len(output_rows),
        "errors": sum(1 for row in output_rows if row.get("error")),
        "embeddings_dir": str(embed_dir),
        "selected_analyses": selected,
    }
    (out_dir / "extract_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
