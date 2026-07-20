#!/usr/bin/env python3
"""Top-up score matrix to exactly TARGET unique rows per (dataset, generator, label)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src" / "backend"))

from audio_lr_dataset_utils import (  # noqa: E402
    bonafide_pool_for,
    infer_generator,
    label_to_y_spoof,
    load_config,
    resolve_audio_path,
    spoof_pool_for,
)
from audio_lr_disk_verify import TARGET_PER_CLASS  # noqa: E402
from core.audio_spoofing_lr_reference import REFERENCE_GENERATORS  # noqa: E402
from core.latent_typicality.representations_utils import source_id_stem  # noqa: E402


def _load_protocol(protocol_csv: Path, datasets: set[str]) -> pd.DataFrame:
    chunks: list[pd.DataFrame] = []
    for chunk in pd.read_csv(protocol_csv, chunksize=200_000, low_memory=False):
        chunk = chunk[chunk["status"].fillna("").eq("ok")].copy()
        chunk = chunk[chunk["dataset"].isin(datasets)].copy()
        if chunk.empty:
            continue
        chunk["generator"] = chunk.apply(lambda row: infer_generator(row.to_dict()), axis=1)
        chunk["y_spoof"] = chunk["label"].map(label_to_y_spoof).astype(int)
        chunks.append(chunk)
    return pd.concat(chunks, ignore_index=True)


def _pool_row_to_score_row(rec: dict, config: dict) -> dict | None:
    audio_path = resolve_audio_path(str(rec.get("file_path") or ""), config)
    if not audio_path.is_file():
        return None
    label = str(rec.get("label") or "").lower()
    return {
        "dataset": str(rec.get("dataset", "")),
        "generator": str(rec.get("generator", "")),
        "purpose": "reference_population",
        "reference_split": "reference_population",
        "subset": str(rec.get("subset", "")),
        "label": label,
        "label_name": label,
        "y_spoof": int(rec.get("y_spoof", 1 if label == "spoof" else 0)),
        "source_id": str(rec.get("source_id") or source_id_stem(audio_path.name)),
        "source_path": str(rec.get("file_path", "")),
        "audio_path": str(audio_path),
        "augmentation": "",
        "error": "",
    }


def topup_matrix(
    *,
    score_matrix: Path,
    protocol_csv: Path,
    config: dict,
    target_per_class: int = TARGET_PER_CLASS,
) -> tuple[pd.DataFrame, dict]:
    existing = pd.read_csv(score_matrix, low_memory=False) if score_matrix.is_file() else pd.DataFrame()
    if "error" in existing.columns:
        ok_existing = existing[existing["error"].fillna("").eq("")].copy()
        errors = existing[existing["error"].fillna("").ne("")].copy()
    else:
        ok_existing = existing.copy()
        errors = pd.DataFrame()

    protocol = _load_protocol(protocol_csv, set(REFERENCE_GENERATORS.keys()))
    kept_rows: list[dict] = []
    added_rows: list[dict] = []
    report: list[dict] = []

    for dataset, generators in REFERENCE_GENERATORS.items():
        for generator in generators:
            for label in ("bonafide", "spoof"):
                sub = ok_existing[
                    ok_existing["dataset"].astype(str).eq(dataset)
                    & ok_existing["generator"].astype(str).eq(generator)
                    & ok_existing["label"].astype(str).str.lower().eq(label)
                ]
                seen: set[str] = set()
                unique_rows: list[dict] = []
                for rec in sub.to_dict(orient="records"):
                    sid = source_id_stem(str(rec.get("source_id") or ""))
                    if sid in seen:
                        continue
                    audio = str(rec.get("audio_path") or "")
                    if not audio or not Path(audio).is_file():
                        continue
                    seen.add(sid)
                    unique_rows.append(rec)
                    if len(unique_rows) >= target_per_class:
                        break

                need = target_per_class - len(unique_rows)
                if need > 0:
                    pool = (
                        bonafide_pool_for(dataset, generator, protocol)
                        if label == "bonafide"
                        else spoof_pool_for(dataset, generator, protocol)
                    )
                    for rec in pool.to_dict(orient="records"):
                        if need <= 0:
                            break
                        sid = source_id_stem(str(rec.get("source_id") or ""))
                        if sid in seen:
                            continue
                        row = _pool_row_to_score_row(rec, config)
                        if not row:
                            continue
                        seen.add(sid)
                        unique_rows.append(row)
                        added_rows.append(row)
                        need -= 1

                # Only already-scored unique rows stay in the matrix. Newly selected
                # pool rows have no detector scores yet and MUST NOT be written into
                # the matrix as placeholders (that was the source of NaN rows). They
                # go to a separate worklist to be scored before re-entering the matrix.
                kept_rows.extend(unique_rows[:target_per_class])
                report.append(
                    {
                        "dataset": dataset,
                        "generator": generator,
                        "label": label,
                        "final_count": min(len(unique_rows), target_per_class),
                        "target": target_per_class,
                        "shortfall": max(0, target_per_class - len(unique_rows)),
                    }
                )

    out = pd.DataFrame(kept_rows)
    if not errors.empty:
        out = pd.concat([out, errors], ignore_index=True)
    worklist = pd.DataFrame(added_rows)

    summary = {
        "rows_before": int(len(existing)),
        "rows_after": int(len(out)),
        "worklist_rows": len(added_rows),
        "shortfalls": [r for r in report if r["shortfall"] > 0],
        "report": report,
    }
    return out, worklist, summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/audio_lr_protocolo.yaml")
    parser.add_argument("--protocol-csv", default="protocolo_unificado.csv")
    parser.add_argument(
        "--score-matrix",
        default="outputs/lr_calibration/audio_spoofing/score_matrices/lr_scores_balanced_full.csv",
    )
    parser.add_argument("--backup", action="store_true", default=True)
    args = parser.parse_args()

    config = load_config(ROOT / args.config)
    score_matrix = ROOT / args.score_matrix
    protocol_csv = ROOT / args.protocol_csv

    if args.backup and score_matrix.is_file():
        import shutil
        from datetime import datetime, timezone

        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = score_matrix.with_suffix(f".csv.bak-{ts}")
        shutil.copy2(score_matrix, backup)

    out_df, worklist_df, summary = topup_matrix(
        score_matrix=score_matrix, protocol_csv=protocol_csv, config=config
    )
    score_matrix.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(score_matrix, index=False)
    worklist_path = score_matrix.with_suffix(".score_worklist.csv")
    if not worklist_df.empty:
        worklist_df.to_csv(worklist_path, index=False)
        summary["worklist_csv"] = str(worklist_path)
    summary_path = score_matrix.with_suffix(".topup_summary.json")
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
