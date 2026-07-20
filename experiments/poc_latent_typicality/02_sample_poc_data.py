#!/usr/bin/env python3
"""Sample balanced POC datasets from protocolo_unificado.csv."""

from __future__ import annotations

import argparse
import json
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

import lib.bootstrap  # noqa: F401
from audio_lr_dataset_utils import (
    assign_purpose_splits,
    audio_duration_seconds,
    build_manifest_rows,
    infer_generator,
    label_to_y_spoof,
    load_config,
    resolve_audio_path,
    sample_generator_balanced,
    write_json,
    write_manifest,
)


def load_poc_config(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def read_dataset_rows(protocol_csv: Path, dataset: str, subset: str | None) -> pd.DataFrame:
    chunks: list[pd.DataFrame] = []
    for chunk in pd.read_csv(protocol_csv, chunksize=200_000, low_memory=False):
        chunk = chunk[chunk["status"].fillna("").eq("ok")].copy()
        chunk = chunk[chunk["dataset"].astype(str).eq(dataset)].copy()
        if subset is not None:
            if subset == "*":
                pass
            elif subset:
                chunk = chunk[chunk["subset"].astype(str).eq(subset)].copy()
            else:
                chunk = chunk[chunk["subset"].isna() | chunk["subset"].astype(str).isin(("", "nan", "None"))].copy()
        if chunk.empty:
            continue
        chunk["generator"] = chunk.apply(lambda row: infer_generator(row.to_dict()), axis=1)
        chunk["y_spoof"] = chunk["label"].map(label_to_y_spoof).astype(int)
        chunks.append(chunk)
    if not chunks:
        raise RuntimeError(f"Nenhuma linha para dataset={dataset!r}, subset={subset!r}")
    return pd.concat(chunks, ignore_index=True)


def _row_passes_duration(row: pd.Series, config: dict[str, Any], min_seconds: float) -> bool:
    resolved = resolve_audio_path(str(row["file_path"]), config)
    if not resolved.exists():
        return False
    if min_seconds <= 0:
        return True
    duration = audio_duration_seconds(resolved)
    return duration is not None and duration >= min_seconds


def _validate_row(row: pd.Series, config: dict[str, Any], min_seconds: float) -> pd.Series | None:
    if not _row_passes_duration(row, config, min_seconds):
        return None
    return row


def build_valid_pool(
    pool: pd.DataFrame,
    config: dict[str, Any],
    min_seconds: float,
    cache_path: Path,
    *,
    workers: int = 16,
) -> pd.DataFrame:
    if cache_path.exists():
        cached = pd.read_csv(cache_path, low_memory=False)
        if len(cached) > 0:
            return cached

    if min_seconds <= 0:
        pool.to_csv(cache_path, index=False)
        return pool

    valid_rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(_validate_row, pool.loc[idx], config, min_seconds): idx
            for idx in pool.index
        }
        for future in as_completed(futures):
            row = future.result()
            if row is not None:
                valid_rows.append(row.to_dict())

    if not valid_rows:
        raise RuntimeError(f"Nenhum arquivo válido em {cache_path.stem}")

    valid = pd.DataFrame(valid_rows)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    valid.to_csv(cache_path, index=False)
    return valid


def sample_class_duration(
    pool: pd.DataFrame,
    n: int,
    rng: random.Random,
    config: dict[str, Any],
    min_seconds: float,
    cache_path: Path,
) -> pd.DataFrame:
    valid = build_valid_pool(pool, config, min_seconds, cache_path)
    if len(valid) >= n:
        return valid.sample(n=n, random_state=rng.randint(0, 2**31 - 1)).reset_index(drop=True)
    if valid.empty:
        raise RuntimeError(f"Pool vazio em {cache_path.stem}")
    return valid.sample(n=n, replace=True, random_state=rng.randint(0, 2**31 - 1)).reset_index(drop=True)


def sample_balanced_duration(
    df: pd.DataFrame,
    *,
    dataset: str,
    generator: str,
    per_class: int,
    seed: int,
    config: dict[str, Any],
    min_seconds: float,
    cache_dir: Path,
) -> pd.DataFrame:
    rng = random.Random(seed)
    bonafide_pool = df[
        df["dataset"].eq(dataset)
        & (df["generator"].eq(generator) | df["subset"].astype(str).eq(generator))
        & df["label"].astype(str).str.lower().eq("bonafide")
    ]
    spoof_pool = df[
        df["dataset"].eq(dataset)
        & (df["generator"].eq(generator) | df["subset"].astype(str).eq(generator))
        & df["label"].astype(str).str.lower().eq("spoof")
    ]
    bonafide = sample_class_duration(
        bonafide_pool,
        per_class,
        rng,
        config,
        min_seconds,
        cache_dir / f"{dataset}__{generator}__bonafide.csv",
    )
    spoof = sample_class_duration(
        spoof_pool,
        per_class,
        rng,
        config,
        min_seconds,
        cache_dir / f"{dataset}__{generator}__spoof.csv",
    )
    bonafide = bonafide.copy()
    spoof = spoof.copy()
    bonafide["sample_generator"] = generator
    spoof["sample_generator"] = generator
    return pd.concat([bonafide, spoof], ignore_index=True)


def sample_poc_dataset(
    protocol_csv: Path,
    *,
    dataset: str,
    subset: str | None,
    generator: str,
    per_class: int,
    seed: int,
    audio_config: dict[str, Any],
    cache_dir: Path,
) -> pd.DataFrame:
    min_seconds = float(audio_config.get("min_duration_seconds", 0) or 0)

    if dataset == "SONAR" and generator != "real_samples":
        full_df = read_dataset_rows(protocol_csv, dataset, subset="*")
        spoof_df = read_dataset_rows(protocol_csv, dataset, subset=subset or generator)
        spoof_df = spoof_df[spoof_df["label"].astype(str).str.lower().eq("spoof")].copy()
        bonafide_pool = full_df[
            full_df["generator"].eq("real_samples")
            & full_df["label"].astype(str).str.lower().eq("bonafide")
        ].copy()
        rng = random.Random(seed)
        bonafide = sample_class_duration(
            bonafide_pool,
            per_class,
            rng,
            audio_config,
            min_seconds,
            cache_dir / f"SONAR__real_samples__bonafide.csv",
        )
        spoof = sample_class_duration(
            spoof_df,
            per_class,
            rng,
            audio_config,
            min_seconds,
            cache_dir / f"SONAR__{generator}__spoof.csv",
        )
        bonafide = bonafide.copy()
        spoof = spoof.copy()
        bonafide["sample_generator"] = generator
        spoof["sample_generator"] = generator
        bonafide["generator"] = generator
        spoof["generator"] = generator
        return pd.concat([bonafide, spoof], ignore_index=True)

    df = read_dataset_rows(protocol_csv, dataset, subset)
    if min_seconds > 0:
        return sample_balanced_duration(
            df,
            dataset=dataset,
            generator=generator,
            per_class=per_class,
            seed=seed,
            config=audio_config,
            min_seconds=min_seconds,
            cache_dir=cache_dir,
        )
    return sample_generator_balanced(
        df,
        dataset=dataset,
        generator=generator,
        per_class=per_class,
        seed=seed,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="experiments/poc_latent_typicality/config/poc_typicality.yaml")
    parser.add_argument("--out-dir", default="")
    args = parser.parse_args()

    poc = load_poc_config(Path(args.config))
    project_root = Path(__file__).resolve().parents[2]
    protocol_csv = project_root / poc.get("protocol_csv", "protocolo_unificado.csv")
    audio_config = load_config(project_root / poc.get("audio_config", "config/audio_lr_protocolo.yaml"))

    train_n = int(poc["n_train_real_per_dataset"])
    calib_n = int(poc["n_val_real_per_dataset"])
    test_n = int(poc["n_test_real_per_dataset"])
    per_class_total = train_n + calib_n + test_n
    seed = int(poc.get("random_seed", 42))

    out_dir = Path(args.out_dir) if args.out_dir else project_root / poc["output_root"] / "sampled"
    cache_dir = out_dir / "valid_pools"
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    parts: list[pd.DataFrame] = []
    for idx, spec in enumerate(poc["datasets"]):
        dataset = str(spec["dataset"])
        subset = spec.get("subset")
        generator = str(spec.get("generator") or subset or dataset)
        sampled = sample_poc_dataset(
            protocol_csv,
            dataset=dataset,
            subset=subset,
            generator=generator,
            per_class=per_class_total,
            seed=seed + idx,
            audio_config=audio_config,
            cache_dir=cache_dir,
        )
        split_df = assign_purpose_splits(
            sampled,
            train_per_class=train_n,
            calib_per_class=calib_n,
            test_per_class=test_n,
            seed=seed + idx + 17,
            group_cols=("dataset", "generator"),
        )
        split_df["sample_id"] = split_df.apply(
            lambda row: f"{row['dataset']}__{row['generator']}__{Path(str(row['file_path'])).stem}",
            axis=1,
        )
        parts.append(split_df)

    merged = pd.concat(parts, ignore_index=True).sample(frac=1.0, random_state=seed).reset_index(drop=True)

    rows = build_manifest_rows(merged, audio_config, copy_files=False, out_dir=out_dir)
    manifest_path = out_dir / "manifest.csv"
    write_manifest(manifest_path, rows)

    summary = {
        "manifest": str(manifest_path),
        "rows": len(rows),
        "datasets": poc["datasets"],
        "train_per_class": train_n,
        "calib_per_class": calib_n,
        "test_per_class": test_n,
        "seed": seed,
    }
    write_json(out_dir / "sample_summary.json", summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
