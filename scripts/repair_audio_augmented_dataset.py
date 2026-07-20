#!/usr/bin/env python3
"""Deduplicate augmented audio manifest, report gaps, and fill missing WAVs only.

Does NOT run detector scoring.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import librosa
import numpy as np
import pandas as pd
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from audio_lr_augmentation import AUGMENTATIONS, apply_augmentation, params_json
from audio_lr_dataset_utils import safe_name, sha256_file, write_json, write_manifest
from augment_audio_lr_dataset import (  # noqa: E402
    _augmentations_complete,
    _manifest_key,
    _manifest_rows_for_source,
    _output_relative,
    rebuild_manifest_from_disk,
)


def _aug_base(out_dir: Path, row_dict: dict[str, Any]) -> Path:
    return (
        out_dir
        / str(row_dict.get("purpose") or "reference_population")
        / safe_name(str(row_dict.get("dataset") or ""))
        / safe_name(str(row_dict.get("generator") or ""))
        / safe_name(str(row_dict.get("label") or ""))
        / "augmented"
    )


def _existing_aug_path(
    out_dir: Path,
    row_dict: dict[str, Any],
    source_id: str,
    aug: str,
) -> Path | None:
    aug_dir = _aug_base(out_dir, row_dict) / safe_name(aug)
    sid = safe_name(source_id)
    matches = sorted(aug_dir.glob(f"{sid}__{safe_name(aug)}__*.wav"))
    if not matches:
        return None
    return matches[-1]


def audit_gaps(
    *,
    score_matrix: Path,
    out_dir: Path,
    augmentations: tuple[str, ...] = AUGMENTATIONS,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    df = pd.read_csv(score_matrix, low_memory=False)
    if "error" in df.columns:
        df = df[df["error"].fillna("").eq("")].copy()

    missing_rows: list[dict[str, Any]] = []
    complete_sources = 0
    partial_sources = 0
    missing_audio = 0
    per_aug_missing: Counter[str] = Counter()
    per_dataset_missing: Counter[str] = Counter()

    for row in df.itertuples(index=False):
        row_dict = row._asdict()
        audio_path = Path(str(row_dict.get("audio_path") or ""))
        source_id = str(row_dict.get("source_id") or audio_path.stem)
        dataset = str(row_dict.get("dataset") or "")
        generator = str(row_dict.get("generator") or "")
        label = str(row_dict.get("label") or "")

        if not audio_path.is_file():
            missing_audio += 1
            missing_rows.append(
                {
                    "dataset": dataset,
                    "generator": generator,
                    "label": label,
                    "source_id": source_id,
                    "augmentation": "*",
                    "reason": "source_audio_missing",
                    "audio_path": str(audio_path),
                }
            )
            continue

        missing_augs: list[str] = []
        for aug in augmentations:
            if _existing_aug_path(out_dir, row_dict, source_id, aug) is None:
                missing_augs.append(aug)
                per_aug_missing[aug] += 1
                per_dataset_missing[dataset] += 1
                missing_rows.append(
                    {
                        "dataset": dataset,
                        "generator": generator,
                        "label": label,
                        "source_id": source_id,
                        "augmentation": aug,
                        "reason": "wav_missing",
                        "audio_path": str(audio_path),
                    }
                )

        if not missing_augs:
            complete_sources += 1
        elif len(missing_augs) < len(augmentations):
            partial_sources += 1

    gaps_df = pd.DataFrame(missing_rows)
    wav_count = sum(1 for _ in out_dir.rglob("*.wav"))
    summary = {
        "score_matrix": str(score_matrix),
        "out_dir": str(out_dir),
        "source_rows": int(len(df)),
        "augmentations": list(augmentations),
        "expected_wavs": int(len(df) * len(augmentations)),
        "wav_files_on_disk": wav_count,
        "complete_sources": complete_sources,
        "partial_sources": partial_sources,
        "missing_audio_sources": missing_audio,
        "missing_aug_total": int(len(gaps_df[gaps_df["reason"] == "wav_missing"])) if len(gaps_df) else 0,
        "missing_by_augmentation": dict(per_aug_missing),
        "missing_by_dataset": dict(per_dataset_missing),
    }
    return gaps_df, summary


def fill_missing_augmentations(
    *,
    score_matrix: Path,
    out_dir: Path,
    gaps_df: pd.DataFrame,
    augmentations: tuple[str, ...] = AUGMENTATIONS,
) -> dict[str, Any]:
    if gaps_df.empty:
        return {"generated": 0, "errors": 0, "by_augmentation": {}}

    df = pd.read_csv(score_matrix, low_memory=False)
    if "error" in df.columns:
        df = df[df["error"].fillna("").eq("")].copy()
    by_source: dict[str, dict[str, Any]] = {}
    for row in df.itertuples(index=False):
        row_dict = row._asdict()
        source_id = str(row_dict.get("source_id") or Path(str(row_dict.get("audio_path") or "")).stem)
        by_source[source_id] = row_dict

    to_fill = gaps_df[gaps_df["reason"] == "wav_missing"].copy()
    stats: dict[str, Any] = {
        "generated": 0,
        "errors": 0,
        "by_augmentation": {aug: 0 for aug in augmentations},
        "error_samples": [],
    }

    grouped: dict[str, list[str]] = defaultdict(list)
    for item in to_fill.itertuples(index=False):
        grouped[str(item.source_id)].append(str(item.augmentation))

    total = len(grouped)
    for idx, (source_id, augs_needed) in enumerate(sorted(grouped.items()), start=1):
        row_dict = by_source.get(source_id)
        if not row_dict:
            stats["errors"] += len(augs_needed)
            continue
        audio_path = Path(str(row_dict.get("audio_path") or ""))
        if not audio_path.is_file():
            stats["errors"] += len(augs_needed)
            continue

        try:
            source_sha256 = str(row_dict.get("audio_sha256") or sha256_file(audio_path))
            audio, sr = librosa.load(str(audio_path), sr=None, mono=True)
        except Exception as exc:
            stats["errors"] += len(augs_needed)
            if len(stats["error_samples"]) < 20:
                stats["error_samples"].append({"source_id": source_id, "error": repr(exc)})
            continue

        for aug in augs_needed:
            if aug not in augmentations:
                stats["errors"] += 1
                continue
            if _existing_aug_path(out_dir, row_dict, source_id, aug) is not None:
                continue
            try:
                augmented, out_sr, params = apply_augmentation(
                    audio,
                    int(sr),
                    aug,
                    source_id=source_id,
                    source_sha256=source_sha256,
                )
                digest = hashlib.sha256(augmented.astype(np.float32).tobytes()).hexdigest()
                dest_rel = _output_relative(
                    purpose=str(row_dict.get("purpose") or "reference_population"),
                    dataset=str(row_dict.get("dataset") or ""),
                    generator=str(row_dict.get("generator") or ""),
                    label=str(row_dict.get("label") or ""),
                    source_id=source_id,
                    aug=aug,
                    digest=digest,
                )
                dest = out_dir / dest_rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                sf.write(str(dest), augmented, out_sr, subtype="PCM_16")
                stats["generated"] += 1
                stats["by_augmentation"][aug] = int(stats["by_augmentation"].get(aug, 0)) + 1
            except Exception as exc:
                stats["errors"] += 1
                if len(stats["error_samples"]) < 20:
                    stats["error_samples"].append(
                        {"source_id": source_id, "augmentation": aug, "error": repr(exc)}
                    )

        if idx % 25 == 0 or idx == total:
            print(f"Filled {idx}/{total} sources with gaps", flush=True)

    return stats


def dedupe_manifest(manifest_path: Path) -> dict[str, Any]:
    if not manifest_path.is_file():
        return {"before": 0, "after": 0, "removed": 0}

    backup = manifest_path.with_suffix(".csv.bak-dedupe")
    if not backup.exists():
        backup.write_bytes(manifest_path.read_bytes())

    df = pd.read_csv(manifest_path, low_memory=False)
    before = len(df)

    if "dest_relative" in df.columns:
        df = df.drop_duplicates(subset=["dest_relative"], keep="last")
    else:
        df = df.drop_duplicates(keep="last")

    keys_seen: set[tuple[str, str, str, str, str]] = set()
    keep_idx: list[int] = []
    for i, row in df.iterrows():
        key = _manifest_key(row.to_dict())
        if key in keys_seen:
            continue
        keys_seen.add(key)
        keep_idx.append(i)
    df = df.loc[keep_idx].reset_index(drop=True)

    after = len(df)
    df.to_csv(manifest_path, index=False)
    return {"before": before, "after": after, "removed": before - after, "backup": str(backup)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--score-matrix",
        default=str(ROOT / "outputs/lr_calibration/audio_spoofing/score_matrices/lr_scores_balanced_full.csv"),
    )
    parser.add_argument(
        "--out-dir",
        default=str(ROOT / "outputs/lr_calibration/audio_spoofing/samples/augmented"),
    )
    parser.add_argument("--augmentations", default=",".join(AUGMENTATIONS))
    parser.add_argument("--skip-fill", action="store_true", help="Apenas auditar/deduplicar, sem gerar WAVs")
    args = parser.parse_args()

    augmentations = tuple(item.strip() for item in args.augmentations.split(",") if item.strip())
    score_matrix = Path(args.score_matrix)
    out_dir = Path(args.out_dir)
    report_dir = out_dir / "repair_reports"
    report_dir.mkdir(parents=True, exist_ok=True)

    # Duplicatas na score matrix explicam expected_wavs > wav_files_on_disk
    sm = pd.read_csv(score_matrix, low_memory=False)
    if "error" in sm.columns:
        sm = sm[sm["error"].fillna("").eq("")].copy()
    keys = sm.apply(
        lambda r: (str(r["dataset"]), str(r["generator"]), str(r["label"]), str(r["source_id"])),
        axis=1,
    )
    dup_count = int(len(sm) - keys.nunique())
    duplicate_report = {
        "score_matrix_rows": int(len(sm)),
        "unique_source_keys": int(keys.nunique()),
        "duplicate_rows_in_score_matrix": dup_count,
        "note": (
            "Linhas duplicadas compartilham os mesmos WAVs aumentados; "
            "wav_files_on_disk = unique_keys * 4 quando completo."
        ),
    }
    write_json(report_dir / "score_matrix_duplicates.json", duplicate_report)

    print("=== 1/4 Auditoria de lacunas ===")
    gaps_df, audit_summary = audit_gaps(
        score_matrix=score_matrix,
        out_dir=out_dir,
        augmentations=augmentations,
    )
    gaps_path = report_dir / "missing_augmentations.csv"
    gaps_df.to_csv(gaps_path, index=False)
    audit_path = report_dir / "audit_summary.json"
    write_json(audit_path, audit_summary)
    print(json.dumps(audit_summary, indent=2, ensure_ascii=False))

    fill_stats: dict[str, Any] = {"generated": 0, "skipped": True}
    if not args.skip_fill and audit_summary["missing_aug_total"] > 0:
        print(f"\n=== 2/4 Gerando {audit_summary['missing_aug_total']} augmentations faltantes ===")
        fill_stats = fill_missing_augmentations(
            score_matrix=score_matrix,
            out_dir=out_dir,
            gaps_df=gaps_df,
            augmentations=augmentations,
        )
        fill_stats["skipped"] = False
        write_json(report_dir / "fill_summary.json", fill_stats)
        print(json.dumps(fill_stats, indent=2, ensure_ascii=False))
    else:
        print("\n=== 2/4 Nenhum WAV faltante — pulando geração ===")

    print("\n=== 3/4 Reconstruindo manifest limpo a partir do disco ===")
    rebuild_summary = rebuild_manifest_from_disk(
        score_matrix=score_matrix,
        out_dir=out_dir,
        augmentations=augmentations,
    )

    print("\n=== 4/4 Deduplicando manifest ===")
    dedupe_stats = dedupe_manifest(out_dir / "manifest.csv")

    # Re-audit final
    _, final_audit = audit_gaps(
        score_matrix=score_matrix,
        out_dir=out_dir,
        augmentations=augmentations,
    )
    final_report = {
        "score_matrix_duplicates": duplicate_report,
        "audit_before": audit_summary,
        "fill": fill_stats,
        "rebuild_manifest": rebuild_summary,
        "dedupe_manifest": dedupe_stats,
        "audit_after": final_audit,
        "gaps_csv": str(gaps_path),
    }
    write_json(report_dir / "repair_final_report.json", final_report)
    print("\n=== RELATÓRIO FINAL ===")
    print(json.dumps(final_report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
