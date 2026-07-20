#!/usr/bin/env python3
"""Generate augmented audio variants from an LR score matrix for re-scoring.

Reads successful rows from ``lr_scores_balanced_full.csv``, applies channel augmentations
(mp3, opus, ambient noise) and writes a manifest ready for ``run_audio_spoofing_score_matrix.py``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import librosa
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from audio_lr_augmentation import AUGMENTATIONS, apply_augmentation, params_json
from audio_lr_dataset_utils import safe_name, sha256_file, write_json, write_manifest


def _output_relative(
    *,
    purpose: str,
    dataset: str,
    generator: str,
    label: str,
    source_id: str,
    aug: str,
    digest: str,
) -> Path:
    return Path(
        purpose or "reference_population",
        safe_name(dataset),
        safe_name(generator),
        safe_name(label),
        "augmented",
        safe_name(aug),
        f"{safe_name(source_id)}__{aug}__{digest[:12]}.wav",
    )


def _augmentations_complete(
    out_dir: Path,
    row_dict: dict[str, Any],
    source_id: str,
    augmentations: tuple[str, ...],
) -> bool:
    base = (
        out_dir
        / str(row_dict.get("purpose") or "reference_population")
        / safe_name(str(row_dict.get("dataset") or ""))
        / safe_name(str(row_dict.get("generator") or ""))
        / safe_name(str(row_dict.get("label") or ""))
        / "augmented"
    )
    sid = safe_name(source_id)
    for aug in augmentations:
        aug_dir = base / safe_name(aug)
        if not any(aug_dir.glob(f"{sid}__{safe_name(aug)}__*.wav")):
            return False
    return True


def _manifest_rows_for_source(
    *,
    out_dir: Path,
    row_dict: dict[str, Any],
    source_id: str,
    augmentations: tuple[str, ...],
    audio_path: Path,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    base = (
        out_dir
        / str(row_dict.get("purpose") or "reference_population")
        / safe_name(str(row_dict.get("dataset") or ""))
        / safe_name(str(row_dict.get("generator") or ""))
        / safe_name(str(row_dict.get("label") or ""))
        / "augmented"
    )
    sid = safe_name(source_id)
    source_sha256 = str(row_dict.get("audio_sha256") or "")
    for aug in augmentations:
        aug_dir = base / safe_name(aug)
        matches = sorted(aug_dir.glob(f"{sid}__{safe_name(aug)}__*.wav"))
        if not matches:
            continue
        dest = matches[-1]
        digest = dest.stem.rsplit("__", 1)[-1]
        dest_rel = dest.relative_to(out_dir)
        rows.append(
            {
                "purpose": row_dict.get("purpose", "reference_population"),
                "reference_split": row_dict.get("reference_split", "reference_population"),
                "dataset": row_dict.get("dataset", ""),
                "generator": row_dict.get("generator", ""),
                "subset": row_dict.get("subset", ""),
                "label": row_dict.get("label", ""),
                "label_name": row_dict.get("label_name") or row_dict.get("label", ""),
                "y_spoof": row_dict.get("y_spoof", 1 if row_dict.get("label") == "spoof" else 0),
                "source_id": f"{source_id}_{aug}",
                "source_path": str(row_dict.get("source_path") or audio_path),
                "resolved_path": str(dest),
                "dest_relative": dest_rel.as_posix(),
                "sha256": digest,
                "bytes": dest.stat().st_size,
                "sync_status": "augmented",
                "augmentation": aug,
                "augmentation_params": "",
                "source_sha256": source_sha256,
                "parent_source_id": source_id,
            }
        )
    return rows


def _manifest_key(row: dict[str, Any]) -> tuple[str, str, str, str, str]:
    parent = str(row.get("parent_source_id") or row.get("source_id") or "")
    return (
        str(row.get("dataset") or ""),
        str(row.get("generator") or ""),
        str(row.get("label") or ""),
        parent,
        str(row.get("augmentation") or ""),
    )


def rebuild_manifest_from_disk(
    *,
    score_matrix: Path,
    out_dir: Path,
    augmentations: tuple[str, ...] = AUGMENTATIONS,
) -> dict[str, Any]:
    """Rebuild manifest.csv from score matrix + WAVs already on disk (fresh, no merge)."""
    df = pd.read_csv(score_matrix, low_memory=False)
    if "error" in df.columns:
        df = df[df["error"].fillna("").eq("")].copy()

    by_key: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    complete_sources = 0
    partial_sources = 0

    for row in df.itertuples(index=False):
        row_dict = row._asdict()
        audio_path = Path(str(row_dict.get("audio_path") or ""))
        source_id = str(row_dict.get("source_id") or audio_path.stem)
        if _augmentations_complete(out_dir, row_dict, source_id, augmentations):
            complete_sources += 1
        else:
            partial_sources += 1
        for manifest_row in _manifest_rows_for_source(
            out_dir=out_dir,
            row_dict=row_dict,
            source_id=source_id,
            augmentations=augmentations,
            audio_path=audio_path,
        ):
            key = _manifest_key(manifest_row)
            by_key[key] = manifest_row

    output_rows = list(by_key.values())
    manifest_path = out_dir / "manifest.csv"
    write_manifest(manifest_path, output_rows)
    summary = {
        "manifest_rows": len(output_rows),
        "source_rows": int(len(df)),
        "complete_sources": complete_sources,
        "partial_sources": partial_sources,
        "expected_unique_wavs": int(len(by_key)),
        "wav_files_on_disk": sum(1 for _ in out_dir.rglob("*.wav")),
    }
    write_json(out_dir / "manifest_rebuild_summary.json", summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return summary


def _load_existing_manifest(out_dir: Path) -> list[dict[str, Any]]:
    manifest_path = out_dir / "manifest.csv"
    if not manifest_path.is_file():
        return []
    df = pd.read_csv(manifest_path, low_memory=False)
    return df.to_dict(orient="records")


def augment_score_matrix(
    *,
    score_matrix: Path,
    out_dir: Path,
    augmentations: tuple[str, ...] = AUGMENTATIONS,
    limit: int = 0,
    force: bool = False,
    resume: bool = False,
) -> dict[str, Any]:
    if out_dir.exists() and force:
        import shutil

        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(score_matrix, low_memory=False)
    if "error" in df.columns:
        df = df[df["error"].fillna("").eq("")].copy()
    if limit > 0:
        df = df.head(limit).copy()

    output_rows: list[dict[str, Any]] = _load_existing_manifest(out_dir) if resume else []
    stats: dict[str, Any] = {
        "source_score_matrix": str(score_matrix),
        "out_dir": str(out_dir),
        "source_rows": int(len(df)),
        "augmentations": list(augmentations),
        "generated": {aug: 0 for aug in augmentations},
        "skipped_complete": 0,
        "errors": 0,
        "resume": resume,
    }

    for idx, row in enumerate(df.itertuples(index=False), start=1):
        row_dict = row._asdict()
        audio_path = Path(str(row_dict.get("audio_path") or ""))
        source_id = str(row_dict.get("source_id") or audio_path.stem)
        if resume and _augmentations_complete(out_dir, row_dict, source_id, augmentations):
            stats["skipped_complete"] += 1
            for manifest_row in _manifest_rows_for_source(
                out_dir=out_dir,
                row_dict=row_dict,
                source_id=source_id,
                augmentations=augmentations,
                audio_path=audio_path,
            ):
                key = (
                    str(manifest_row.get("dataset") or ""),
                    str(manifest_row.get("generator") or ""),
                    str(manifest_row.get("label") or ""),
                    str(manifest_row.get("parent_source_id") or source_id),
                    str(manifest_row.get("augmentation") or ""),
                )
                if not any(
                    _manifest_key(existing) == key
                    for existing in output_rows
                ):
                    output_rows.append(manifest_row)
            if idx % 50 == 0:
                print(f"Processed {idx}/{len(df)} source rows", flush=True)
            continue
        if not audio_path.is_file():
            stats["errors"] += 1
            continue

        try:
            source_sha256 = str(row_dict.get("audio_sha256") or sha256_file(audio_path))
            audio, sr = librosa.load(str(audio_path), sr=None, mono=True)
        except Exception as exc:
            stats["errors"] += 1
            print(f"[WARN] Cannot load {audio_path}: {exc}")
            continue

        for aug in augmentations:
            try:
                augmented, out_sr, params = apply_augmentation(
                    audio,
                    int(sr),
                    aug,
                    source_id=source_id,
                    source_sha256=source_sha256,
                )
                import hashlib

                payload = augmented.astype(np.float32).tobytes()
                digest = hashlib.sha256(payload).hexdigest()
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
                import soundfile as sf

                sf.write(str(dest), augmented, out_sr, subtype="PCM_16")

                output_rows.append(
                    {
                        "purpose": row_dict.get("purpose", "reference_population"),
                        "reference_split": row_dict.get("reference_split", "reference_population"),
                        "dataset": row_dict.get("dataset", ""),
                        "generator": row_dict.get("generator", ""),
                        "subset": row_dict.get("subset", ""),
                        "label": row_dict.get("label", ""),
                        "label_name": row_dict.get("label_name") or row_dict.get("label", ""),
                        "y_spoof": row_dict.get("y_spoof", 1 if row_dict.get("label") == "spoof" else 0),
                        "source_id": f"{source_id}_{aug}",
                        "source_path": str(row_dict.get("source_path") or audio_path),
                        "resolved_path": str(dest),
                        "dest_relative": dest_rel.as_posix(),
                        "sha256": digest,
                        "bytes": dest.stat().st_size,
                        "sync_status": "augmented",
                        "augmentation": aug,
                        "augmentation_params": params_json(params),
                        "source_sha256": source_sha256,
                        "parent_source_id": source_id,
                    }
                )
                stats["generated"][aug] += 1
            except Exception as exc:
                stats["errors"] += 1
                print(f"[WARN] {aug} failed for {audio_path}: {exc}")

        if idx % 50 == 0:
            print(f"Processed {idx}/{len(df)} source rows", flush=True)
            if output_rows:
                write_manifest(out_dir / "manifest.csv", output_rows)

    manifest_path = out_dir / "manifest.csv"
    write_manifest(manifest_path, output_rows)
    write_json(out_dir / "summary.json", stats)
    print(json.dumps(stats, indent=2, sort_keys=True, ensure_ascii=False))
    return stats


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
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--resume", action="store_true", help="Pular fontes com 4 augmentations ja geradas")
    parser.add_argument(
        "--rebuild-manifest",
        action="store_true",
        help="Reconstruir manifest.csv a partir dos WAVs existentes (sem gerar novos)",
    )
    args = parser.parse_args()

    augmentations = tuple(item.strip() for item in args.augmentations.split(",") if item.strip())
    for aug in augmentations:
        if aug not in AUGMENTATIONS:
            raise ValueError(f"Unknown augmentation '{aug}'. Supported: {AUGMENTATIONS}")

    if args.rebuild_manifest:
        rebuild_manifest_from_disk(
            score_matrix=Path(args.score_matrix),
            out_dir=Path(args.out_dir),
            augmentations=augmentations,
        )
        return

    augment_score_matrix(
        score_matrix=Path(args.score_matrix),
        out_dir=Path(args.out_dir),
        augmentations=augmentations,
        limit=args.limit,
        force=args.force,
        resume=args.resume,
    )


if __name__ == "__main__":
    main()
