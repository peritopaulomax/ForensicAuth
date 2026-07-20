#!/usr/bin/env python3
"""Extract detector scores and penultimate-layer embeddings."""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path
from typing import Any

import librosa
import numpy as np
import yaml

import lib.bootstrap  # noqa: F401
from audio_lr_dataset_utils import DETECTORS, manifest_input_path, read_manifest
from core.legacy.audio_spoofing.pipeline import run_audio_spoofing_analysis


def load_poc_config(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="experiments/poc_latent_typicality/config/poc_typicality.yaml")
    parser.add_argument("--manifest", default="")
    parser.add_argument("--out-dir", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[2]
    poc = load_poc_config(project_root / args.config)
    out_dir = Path(args.out_dir) if args.out_dir else project_root / poc["output_root"] / "representations"
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = Path(args.manifest) if args.manifest else project_root / poc["output_root"] / "sampled/manifest.csv"

    rows = read_manifest(manifest)
    if args.limit > 0:
        rows = rows[: args.limit]

    meta_path = out_dir / "representations.csv"
    embed_dir = out_dir / "embeddings"
    embed_dir.mkdir(parents=True, exist_ok=True)

    existing: dict[str, dict[str, str]] = {}
    if args.resume and meta_path.exists():
        with meta_path.open(encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                if not row.get("error"):
                    existing[row["sample_id"]] = row

    output_rows: list[dict[str, Any]] = list(existing.values())
    done_ids = set(existing)

    for idx, row in enumerate(rows, start=1):
        sample_id = row.get("source_id") or Path(row.get("source_path", "")).stem
        dataset = row.get("dataset", "")
        generator = row.get("generator", "")
        sample_id = f"{dataset}__{generator}__{sample_id}"
        if sample_id in done_ids:
            continue

        path = manifest_input_path(row)
        out_row: dict[str, Any] = {
            "sample_id": sample_id,
            "dataset": dataset,
            "generator": generator,
            "purpose": row.get("purpose", ""),
            "reference_split": row.get("reference_split", row.get("purpose", "")),
            "label": row.get("label", ""),
            "label_name": row.get("label_name", row.get("label", "")),
            "y_spoof": int(row.get("y_spoof", "1" if row.get("label") == "spoof" else "0")),
            "source_path": row.get("source_path", ""),
            "audio_path": str(path),
            "error": "",
            "elapsed_seconds": "",
        }

        if not path.exists():
            out_row["error"] = f"FileNotFoundError: {path}"
            output_rows.append(out_row)
            continue

        start = time.time()
        try:
            audio, sr = librosa.load(str(path), sr=None, mono=True)
            result = run_audio_spoofing_analysis(
                audio=np.asarray(audio, dtype=np.float32),
                sr=int(sr),
                window_seconds=float(poc.get("window_seconds", 4.0)),
                return_embedding=True,
            )
            for detector_id in DETECTORS:
                scores = (result.get("detector_scores") or {}).get(detector_id) or {}
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
        except Exception as exc:
            out_row["error"] = repr(exc)

        out_row["elapsed_seconds"] = f"{time.time() - start:.3f}"
        output_rows.append(out_row)
        done_ids.add(sample_id)

        if idx % 3 == 0 or out_row.get("error"):
            fieldnames = sorted({key for row in output_rows for key in row})
            with meta_path.open("w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(output_rows)
            print(f"Processed {idx}/{len(rows)}", flush=True)

    fieldnames = sorted({key for row in output_rows for key in row})
    with meta_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(output_rows)

    summary = {
        "representations_csv": str(meta_path),
        "rows": len(output_rows),
        "errors": sum(1 for row in output_rows if row.get("error")),
        "embeddings_dir": str(embed_dir),
    }
    (out_dir / "extract_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    sys.setrecursionlimit(10000)
    main()
