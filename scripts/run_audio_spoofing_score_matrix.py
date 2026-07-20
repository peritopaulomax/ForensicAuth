#!/usr/bin/env python3
"""Run audio spoofing detectors and build LR score matrices."""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import random
import sys
import time
from pathlib import Path
from typing import Any

import librosa
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "src" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from audio_lr_dataset_utils import DETECTORS, manifest_input_path, read_manifest  # noqa: E402
from core.latent_typicality.representations_utils import source_id_stem  # noqa: E402
from core.legacy.audio_spoofing.pipeline import run_audio_spoofing_analysis  # noqa: E402
from core.legacy.audio_spoofing.runtime import DEFAULT_AUDIO_SPOOFING_ANALYSES  # noqa: E402


def _identity(row: dict[str, Any]) -> tuple[str, str, str, str, str]:
    """Full identity of a scored/manifest row.

    Includes augmentation so originals and augmentations never collide, and the
    generator so shared bonafide pools (same audio reused across generators) are
    kept as distinct rows instead of being deduplicated by path.
    """
    return (
        str(row.get("dataset", "")),
        str(row.get("generator", "")),
        str(row.get("label", "")).strip().lower(),
        source_id_stem(str(row.get("source_id", ""))),
        str(row.get("augmentation", "") or ""),
    )


def _float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if math.isfinite(result):
        return result
    return None


def _row_has_finite_scores(row: dict[str, Any]) -> bool:
    """A scored row is complete only if all detectors have finite bonafide_logit."""
    for detector_id in DETECTORS:
        if _float(row.get(f"{detector_id}_bonafide_logit")) is None:
            return False
    return True


def _init_output_row(row: dict[str, str], path: Path) -> dict[str, Any]:
    out: dict[str, Any] = {
        "dataset": row.get("dataset", ""),
        "purpose": row.get("purpose", ""),
        "reference_split": row.get("reference_split", row.get("purpose", "")),
        "generator": row.get("generator", ""),
        "subset": row.get("subset", ""),
        "label": row.get("label", ""),
        "label_name": row.get("label_name", row.get("label", "")),
        "y_spoof": int(row.get("y_spoof", "1" if row.get("label") == "spoof" else "0")),
        "source_id": row.get("source_id", ""),
        "source_path": row.get("source_path", ""),
        "audio_path": str(path),
        "audio_sha256": row.get("sha256", ""),
        "augmentation": row.get("augmentation", ""),
        "augmentation_params": row.get("augmentation_params", ""),
        "source_sha256": row.get("source_sha256", row.get("sha256", "")),
        "parent_source_id": row.get("parent_source_id", ""),
        "error": "",
        "elapsed_seconds": "",
    }
    for detector_id in DETECTORS:
        out[f"{detector_id}_spoof_prob"] = ""
        out[f"{detector_id}_bonafide_prob"] = ""
        out[f"{detector_id}_spoof_logit"] = ""
        out[f"{detector_id}_bonafide_logit"] = ""
        out[f"{detector_id}_decision"] = ""
        out[f"{detector_id}_device"] = ""
        out[f"{detector_id}_window_count"] = ""
    return out


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Build fieldnames as the union of all row keys (resumed rows may carry a
    # different/older column set than freshly scored rows). Missing values are
    # written as empty strings via restval, and stray keys never crash the writer.
    if rows:
        fieldnames: list[str] = list(rows[0].keys())
        seen = set(fieldnames)
        for row in rows:
            for key in row.keys():
                if key not in seen:
                    seen.add(key)
                    fieldnames.append(key)
    else:
        fieldnames = ["dataset", "error"]
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, restval="", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    os.replace(tmp_path, path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", action="append", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--sample-per-purpose-label", type=int, default=0)
    parser.add_argument("--seed", type=int, default=20260704)
    parser.add_argument(
        "--selected",
        default=",".join(DEFAULT_AUDIO_SPOOFING_ANALYSES),
        help="Detectores separados por vírgula",
    )
    parser.add_argument("--window-seconds", type=float, default=4.0)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    selected = [item.strip() for item in args.selected.split(",") if item.strip()]
    rows: list[dict[str, str]] = []
    for manifest in args.manifest:
        rows.extend(read_manifest(Path(manifest)))

    if args.sample_per_purpose_label > 0:
        grouped: dict[tuple[str, str, str], list[dict[str, str]]] = {}
        for row in rows:
            key = (row.get("dataset", ""), row.get("purpose", ""), row.get("label", ""))
            grouped.setdefault(key, []).append(row)
        rng = random.Random(args.seed)
        sampled: list[dict[str, str]] = []
        for key in sorted(grouped):
            group = grouped[key]
            rng.shuffle(group)
            sampled.extend(group[: args.sample_per_purpose_label])
        rows = sampled
    if args.limit > 0:
        rows = rows[: args.limit]

    out_path = Path(args.out)
    output_rows: list[dict[str, Any]] = []
    done_ids: set[tuple[str, str, str, str, str]] = set()
    if args.resume and out_path.exists():
        with out_path.open(encoding="utf-8") as fh:
            existing = list(csv.DictReader(fh))
        # Keep every genuinely complete row (3 finite logits), keyed by full
        # identity (dataset/generator/label/source_id/augmentation). Rows with
        # NaN/placeholder logits are dropped so they get re-scored. Identity keying
        # (not audio_path) preserves shared bonafide pools reused across generators.
        for row in existing:
            if not _row_has_finite_scores(row):
                continue
            ident = _identity(row)
            if ident in done_ids:
                continue
            output_rows.append(row)
            done_ids.add(ident)

    for idx, row in enumerate(rows, start=1):
        path = manifest_input_path(row)
        if not path.exists():
            out_row = _init_output_row(row, path)
            out_row["error"] = f"FileNotFoundError: {path}"
            output_rows.append(out_row)
            continue
        if _identity(row) in done_ids:
            continue
        done_ids.add(_identity(row))
        out_row = _init_output_row(row, path)
        start = time.time()
        try:
            audio, sr = librosa.load(str(path), sr=None, mono=True)
            result = run_audio_spoofing_analysis(
                audio=np.asarray(audio, dtype=np.float32),
                sr=int(sr),
                window_seconds=float(args.window_seconds),
                selected_analyses=selected,
            )
            for detector_id, scores in (result.get("detector_scores") or {}).items():
                if detector_id not in DETECTORS:
                    continue
                out_row[f"{detector_id}_spoof_prob"] = _float(scores.get("spoof_prob"))
                out_row[f"{detector_id}_bonafide_prob"] = _float(scores.get("bonafide_prob"))
                out_row[f"{detector_id}_spoof_logit"] = _float(scores.get("spoof_logit"))
                out_row[f"{detector_id}_bonafide_logit"] = _float(scores.get("bonafide_logit"))
                out_row[f"{detector_id}_decision"] = scores.get("decision", "")
                out_row[f"{detector_id}_device"] = scores.get("device", "")
                out_row[f"{detector_id}_window_count"] = scores.get("window_count", "")
        except Exception as exc:
            out_row["error"] = repr(exc)
        out_row["elapsed_seconds"] = f"{time.time() - start:.3f}"
        output_rows.append(out_row)
        if idx % 5 == 0:
            _write_csv(out_path, output_rows)
            print(f"Processed {idx}/{len(rows)}", flush=True)

    _write_csv(out_path, output_rows)
    summary = {
        "out": str(out_path),
        "rows": len(output_rows),
        "errors": sum(1 for row in output_rows if row.get("error")),
        "detectors": DETECTORS,
        "selected": selected,
        "window_seconds": args.window_seconds,
    }
    out_path.with_suffix(".summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    os.environ.setdefault("PYTHONHASHSEED", "0")
    main()
