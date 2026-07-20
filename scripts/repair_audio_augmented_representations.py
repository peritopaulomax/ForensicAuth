#!/usr/bin/env python3
"""Repair augmented representations after sample_id collision bug.

Renames mis-keyed embedding .npy files and corrects sample_id/source_id in
``representations/augmented/representations.csv`` using manifest audio paths.
Does NOT re-run GPU inference — only fixes metadata for rows already extracted.

After repair, run incremental extraction::

    python scripts/extract_audio_representations.py --source augmented --resume
    python scripts/merge_audio_representations.py
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src" / "backend"))

from audio_lr_dataset_utils import DETECTORS, read_manifest
from core.latent_typicality.representations_utils import build_sample_id, resolve_parent_source_id


def load_config(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _manifest_path_index(manifest_rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    index: dict[str, dict[str, str]] = {}
    for row in manifest_rows:
        path = str(row.get("resolved_path") or "").strip()
        if path:
            index[path] = row
    return index


def _correct_sample_id(row: dict[str, str]) -> str:
    return build_sample_id(
        dataset=str(row.get("dataset", "")),
        generator=str(row.get("generator", "")),
        source_id=resolve_parent_source_id(row),
        augmentation=str(row.get("augmentation", "") or ""),
    )


def _rename_embedding(
    embed_dir: Path,
    old_sample_id: str,
    new_sample_id: str,
    detector: str,
    *,
    dry_run: bool,
) -> tuple[str, str]:
    """Return (old_path, new_path); rename on disk unless dry_run."""
    old_path = embed_dir / f"{old_sample_id}__{detector}.npy"
    new_path = embed_dir / f"{new_sample_id}__{detector}.npy"
    if old_sample_id == new_sample_id:
        return str(old_path), str(new_path)
    if not old_path.is_file():
        return str(old_path), str(new_path)
    if new_path.is_file():
        return str(old_path), str(new_path)
    if not dry_run:
        new_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(old_path), str(new_path))
    return str(old_path), str(new_path)


def repair_augmented_representations(
    *,
    manifest_path: Path,
    representations_csv: Path,
    embeddings_dir: Path,
    dry_run: bool = False,
    backup: bool = True,
) -> dict[str, Any]:
    manifest_rows = read_manifest(manifest_path)
    path_index = _manifest_path_index(manifest_rows)

    df = pd.read_csv(representations_csv, low_memory=False)
    if backup and not dry_run:
        stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_path = representations_csv.with_suffix(f".csv.bak-{stamp}")
        shutil.copy2(representations_csv, backup_path)
    else:
        backup_path = None

    renamed_embeddings = 0
    rows_fixed = 0
    rows_unchanged = 0
    rows_unmatched = 0
    sample_id_changes: list[dict[str, str]] = []

    for idx, row in df.iterrows():
        audio_path = str(row.get("audio_path") or "").strip()
        manifest_row = path_index.get(audio_path)
        if manifest_row is None:
            rows_unmatched += 1
            continue

        correct_sid = _correct_sample_id(manifest_row)
        correct_source = resolve_parent_source_id(manifest_row)
        old_sid = str(row.get("sample_id") or "")

        if old_sid == correct_sid and str(row.get("source_id") or "") == correct_source:
            rows_unchanged += 1
            continue

        if old_sid != correct_sid:
            sample_id_changes.append(
                {"old_sample_id": old_sid, "new_sample_id": correct_sid, "audio_path": audio_path}
            )
            for detector in DETECTORS:
                col = f"{detector}_embedding_path"
                old_emb, new_emb = _rename_embedding(
                    embeddings_dir,
                    old_sid,
                    correct_sid,
                    detector,
                    dry_run=dry_run,
                )
                if Path(old_emb).is_file() and old_sid != correct_sid:
                    renamed_embeddings += 1
                if col in df.columns:
                    df.at[idx, col] = new_emb

        df.at[idx, "sample_id"] = correct_sid
        df.at[idx, "source_id"] = correct_source
        rows_fixed += 1

    if "error" in df.columns:
        df_ok = df[df["error"].fillna("").eq("")].copy()
    else:
        df_ok = df.copy()

    done_ids = set(df_ok["sample_id"].astype(str))
    missing_manifest: list[dict[str, str]] = []
    missing_by_dataset: dict[str, int] = {}
    for mrow in manifest_rows:
        sid = _correct_sample_id(mrow)
        if sid in done_ids:
            continue
        missing_manifest.append(
            {
                "sample_id": sid,
                "dataset": str(mrow.get("dataset", "")),
                "augmentation": str(mrow.get("augmentation", "")),
                "label": str(mrow.get("label", "")),
            }
        )
        ds = str(mrow.get("dataset", ""))
        missing_by_dataset[ds] = missing_by_dataset.get(ds, 0) + 1

    if not dry_run:
        representations_csv.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(representations_csv, index=False)

    summary: dict[str, Any] = {
        "dry_run": dry_run,
        "backup_path": str(backup_path) if backup_path else None,
        "representations_csv": str(representations_csv),
        "embeddings_dir": str(embeddings_dir),
        "manifest_rows": len(manifest_rows),
        "csv_rows_before": int(len(df)),
        "rows_fixed": rows_fixed,
        "rows_unchanged": rows_unchanged,
        "rows_unmatched_audio_path": rows_unmatched,
        "embedding_files_renamed": renamed_embeddings,
        "unique_sample_id_corrections": len(sample_id_changes),
        "still_missing_extraction": len(missing_manifest),
        "still_missing_by_dataset": dict(sorted(missing_by_dataset.items(), key=lambda x: -x[1])),
    }
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/audio_spoofing_typicality.yaml")
    parser.add_argument("--dry-run", action="store_true", help="Report only; do not rename or write CSV")
    parser.add_argument("--no-backup", action="store_true")
    args = parser.parse_args()

    cfg = load_config(ROOT / args.config)
    manifest = ROOT / cfg["augmented_manifest"]
    aug_dir = ROOT / cfg.get(
        "augmented_embeddings_dir",
        "outputs/lr_calibration/audio_spoofing/representations/augmented",
    )
    representations_csv = aug_dir / "representations.csv"
    embeddings_dir = aug_dir / "embeddings"

    summary = repair_augmented_representations(
        manifest_path=manifest,
        representations_csv=representations_csv,
        embeddings_dir=embeddings_dir,
        dry_run=args.dry_run,
        backup=not args.no_backup,
    )
    report_path = aug_dir / "repair_sample_id_report.json"
    if not args.dry_run:
        report_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
        summary["report_path"] = str(report_path)
    print(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False))


if __name__ == "__main__":
    main()
