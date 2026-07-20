#!/usr/bin/env python3
"""Extract detector scores and penultimate-layer embeddings for audio LR typicality."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

import librosa
import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src" / "backend"))

from audio_lr_dataset_utils import DETECTORS, manifest_input_path, read_manifest
from audio_lr_disk_verify import write_scores_sidecar
from core.latent_typicality.representations_utils import (
    ORIGINAL_AUGMENTATION_TAG,
    build_sample_id,
    resolve_parent_source_id,
    source_id_stem,
)
from core.legacy.audio_spoofing.pipeline import run_audio_spoofing_analysis


def load_config(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _rows_from_augmented_manifest(manifest: Path) -> list[dict[str, str]]:
    rows = read_manifest(manifest)
    for row in rows:
        row["parent_source_id"] = resolve_parent_source_id(row)
    return rows


def _rows_from_score_matrix(score_matrix: Path) -> list[dict[str, str]]:
    df = pd.read_csv(score_matrix, low_memory=False)
    if "error" in df.columns:
        df = df[df["error"].fillna("").eq("")].copy()
    rows: list[dict[str, str]] = []
    for record in df.to_dict(orient="records"):
        rows.append(
            {
                "dataset": str(record.get("dataset", "")),
                "generator": str(record.get("generator", "")),
                "purpose": str(record.get("purpose", "reference_population")),
                "reference_split": str(record.get("reference_split", record.get("purpose", ""))),
                "label": str(record.get("label", "")),
                "label_name": str(record.get("label_name", record.get("label", ""))),
                "y_spoof": str(record.get("y_spoof", "")),
                "source_id": str(record.get("source_id", "")),
                "source_path": str(record.get("source_path", record.get("audio_path", ""))),
                "resolved_path": str(record.get("audio_path", record.get("source_path", ""))),
                "augmentation": "",
                "parent_source_id": str(record.get("source_id", "")),
            }
        )
    return rows


def _is_finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _prefill_scores_from_matrix(out_row: dict[str, Any], record: dict[str, Any] | None) -> None:
    if not record:
        return
    for detector in DETECTORS:
        for suffix in ("bonafide_logit", "spoof_logit", "bonafide_prob"):
            col = f"{detector}_{suffix}"
            # Backfill whenever the current value is missing OR non-finite (NaN/"nan").
            # The detector score is a property of the physical audio file, so the
            # sanitized score-matrix value is exact and safe to (re)write. This is what
            # keeps a resumed run from preserving stale NaN scores.
            if col in record and record[col] not in (None, "") and not _is_finite(out_row.get(col)):
                out_row[col] = record[col]


def _row_scores_finite(row: dict[str, Any]) -> bool:
    """True only if every detector has a finite bonafide_logit (calibration-ready)."""
    return all(_is_finite(row.get(f"{detector}_bonafide_logit")) for detector in DETECTORS)


def _embeddings_on_disk(sample_id: str, embed_dir: Path) -> bool:
    for detector in DETECTORS:
        if not (embed_dir / f"{sample_id}__{detector}.npy").is_file():
            return False
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/audio_spoofing_typicality.yaml")
    parser.add_argument("--source", choices=("augmented", "originals"), required=True)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    cfg = load_config(ROOT / args.config)
    window_seconds = float(cfg.get("window_seconds", 4.0))

    if args.source == "augmented":
        manifest = ROOT / cfg["augmented_manifest"]
        out_dir = ROOT / cfg.get("augmented_embeddings_dir", "outputs/lr_calibration/audio_spoofing/representations/augmented")
        rows = _rows_from_augmented_manifest(manifest)
        score_lookup: dict[str, dict[str, Any]] = {}
    else:
        score_matrix = ROOT / cfg["score_matrix_base"]
        out_dir = ROOT / cfg.get("originals_embeddings_dir", "outputs/lr_calibration/audio_spoofing/representations/originals")
        df_scores = pd.read_csv(score_matrix, low_memory=False)
        if "error" in df_scores.columns:
            df_scores = df_scores[df_scores["error"].fillna("").eq("")].copy()
        score_lookup = {
            build_sample_id(
                dataset=str(r.get("dataset", "")),
                generator=str(r.get("generator", "")),
                source_id=source_id_stem(str(r.get("source_id", ""))),
                augmentation="",
            ): r
            for r in df_scores.to_dict(orient="records")
        }
        rows = _rows_from_score_matrix(score_matrix)

    if args.limit > 0:
        rows = rows[: args.limit]

    out_dir.mkdir(parents=True, exist_ok=True)
    embed_dir = out_dir / "embeddings"
    embed_dir.mkdir(parents=True, exist_ok=True)
    meta_path = out_dir / "representations.csv"

    existing: dict[str, dict[str, str]] = {}
    if args.resume and meta_path.exists():
        with meta_path.open(encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                if row.get("error"):
                    continue
                sid = str(row.get("sample_id") or "")
                if not (sid and _embeddings_on_disk(sid, embed_dir)):
                    continue
                # Refresh stale/NaN scores from the sanitized matrix (no GPU needed;
                # for originals the matrix has the exact score, for augmented the
                # lookup is empty so this is a no-op).
                _prefill_scores_from_matrix(row, score_lookup.get(sid))
                # A resumed row counts as done ONLY when embeddings exist AND all three
                # detector logits are finite. Rows that are still non-finite (e.g. an
                # augmented row with no matrix source) fall through to be re-scored on
                # GPU, so a resumed run can never carry NaN scores forward.
                if _row_scores_finite(row):
                    existing[sid] = row

    output_rows: list[dict[str, Any]] = list(existing.values())
    done_ids = set(existing)

    for idx, row in enumerate(rows, start=1):
        dataset = str(row.get("dataset", ""))
        generator = str(row.get("generator", ""))
        source_id = source_id_stem(str(row.get("parent_source_id") or row.get("source_id") or ""))
        augmentation = str(row.get("augmentation", "") or "")
        sample_id = build_sample_id(
            dataset=dataset,
            generator=generator,
            source_id=source_id,
            augmentation=augmentation,
        )
        if sample_id in done_ids:
            continue

        if args.source == "augmented":
            path = manifest_input_path(row)
        else:
            path = Path(str(row.get("resolved_path") or row.get("source_path") or ""))

        out_row: dict[str, Any] = {
            "sample_id": sample_id,
            "dataset": dataset,
            "generator": generator,
            "purpose": row.get("purpose", "reference_population"),
            "reference_split": row.get("reference_split", row.get("purpose", "")),
            "label": row.get("label", ""),
            "label_name": row.get("label_name", row.get("label", "")),
            "y_spoof": int(row.get("y_spoof", "1" if row.get("label") == "spoof" else 0)),
            "source_id": source_id,
            "source_path": row.get("source_path", ""),
            "audio_path": str(path),
            "augmentation": augmentation or ORIGINAL_AUGMENTATION_TAG,
            "error": "",
            "elapsed_seconds": "",
        }
        _prefill_scores_from_matrix(out_row, score_lookup.get(sample_id))

        if not path.exists():
            out_row["error"] = f"FileNotFoundError: {path}"
            output_rows.append(out_row)
            done_ids.add(sample_id)
            continue

        need_gpu = any(
            out_row.get(f"{detector}_bonafide_logit") in (None, "")
            for detector in DETECTORS
        ) or args.source == "augmented"

        start = time.time()
        try:
            audio, sr = librosa.load(str(path), sr=None, mono=True)
            result = run_audio_spoofing_analysis(
                audio=np.asarray(audio, dtype=np.float32),
                sr=int(sr),
                window_seconds=window_seconds,
                return_embedding=True,
            )
            for detector_id in DETECTORS:
                scores = (result.get("detector_scores") or {}).get(detector_id) or {}
                if need_gpu or out_row.get(f"{detector_id}_bonafide_logit") in (None, ""):
                    out_row[f"{detector_id}_bonafide_logit"] = scores.get("bonafide_logit")
                    out_row[f"{detector_id}_spoof_logit"] = scores.get("spoof_logit")
                    out_row[f"{detector_id}_bonafide_prob"] = scores.get("bonafide_prob")
                embedding = scores.get("embedding")
                if embedding is None:
                    raise RuntimeError(f"Embedding ausente para detector {detector_id}")
                emb_path = embed_dir / f"{sample_id}__{detector_id}.npy"
                np.save(emb_path, np.asarray(embedding, dtype=np.float32))
                out_row[f"{detector_id}_embedding_path"] = str(emb_path)
                out_row[f"{detector_id}_embedding_dim"] = int(np.asarray(embedding).size)
            if not out_row.get("error"):
                write_scores_sidecar(embed_dir, sample_id, out_row)
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
            print(f"Processed {idx}/{len(rows)}", flush=True)

    fieldnames = sorted({key for r in output_rows for key in r})
    with meta_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(output_rows)

    summary = {
        "source": args.source,
        "representations_csv": str(meta_path),
        "rows": len(output_rows),
        "errors": sum(1 for row in output_rows if row.get("error")),
        "embeddings_dir": str(embed_dir),
    }
    (out_dir / "extract_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
