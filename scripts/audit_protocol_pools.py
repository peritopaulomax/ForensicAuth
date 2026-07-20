#!/usr/bin/env python3
"""Audit unique accessible protocol pools per reference generator."""

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
from audio_lr_disk_verify import TARGET_PER_CLASS, UNITS_PER_ELIGIBLE_GENERATOR  # noqa: E402
from core.audio_spoofing_lr_reference import REFERENCE_GENERATORS  # noqa: E402


def load_protocol(protocol_csv: Path, datasets: set[str], *, cache_path: Path | None = None) -> pd.DataFrame:
    if cache_path and cache_path.is_file():
        df = pd.read_pickle(cache_path)
        return df[df["dataset"].isin(datasets)].copy()

    chunks: list[pd.DataFrame] = []
    for chunk in pd.read_csv(protocol_csv, chunksize=200_000, low_memory=False):
        chunk = chunk[chunk["status"].fillna("").eq("ok")].copy()
        chunk = chunk[chunk["dataset"].isin(datasets)].copy()
        if chunk.empty:
            continue
        chunk["generator"] = chunk.apply(lambda row: infer_generator(row.to_dict()), axis=1)
        chunk["y_spoof"] = chunk["label"].map(label_to_y_spoof).astype(int)
        chunks.append(chunk)
    if not chunks:
        raise RuntimeError("Nenhuma linha ok no protocolo para datasets de referencia")
    df = pd.concat(chunks, ignore_index=True)
    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_pickle(cache_path)
    return df


def unique_protocol_ids(pool: pd.DataFrame) -> int:
    """Count unique source ids in protocol (status=ok rows only; no per-file stat)."""
    seen: set[str] = set()
    for rec in pool.to_dict(orient="records"):
        path = str(rec.get("file_path") or "")
        sid = str(rec.get("source_id") or path)
        if not sid:
            continue
        seen.add(sid)
    return len(seen)


def verify_accessible_sample(pool: pd.DataFrame, config: dict, *, max_check: int = 50) -> float:
    """Fraction of sampled paths that exist on disk (0..1)."""
    if pool.empty:
        return 0.0
    sample = pool.head(max_check) if len(pool) <= max_check else pool.sample(n=max_check, random_state=0)
    ok = 0
    for rec in sample.to_dict(orient="records"):
        path = resolve_audio_path(str(rec.get("file_path") or ""), config)
        if path.is_file():
            ok += 1
    return ok / len(sample)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/audio_lr_protocolo.yaml")
    parser.add_argument("--protocol-csv", default="protocolo_unificado.csv")
    parser.add_argument("--out-dir", default="outputs/lr_calibration/audio_spoofing/inventory")
    args = parser.parse_args()

    config = load_config(ROOT / args.config)
    protocol_csv = ROOT / args.protocol_csv
    out_dir = ROOT / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_path = out_dir / "protocol_reference_cache.pkl"
    df = load_protocol(protocol_csv, set(REFERENCE_GENERATORS.keys()), cache_path=cache_path)

    rows: list[dict] = []
    for dataset, generators in REFERENCE_GENERATORS.items():
        for generator in generators:
            bf_pool = bonafide_pool_for(dataset, generator, df)
            sp_pool = spoof_pool_for(dataset, generator, df)
            bf_unique = unique_protocol_ids(bf_pool)
            sp_unique = unique_protocol_ids(sp_pool)
            bf_access = verify_accessible_sample(bf_pool, config)
            sp_access = verify_accessible_sample(sp_pool, config)
            eligible = bf_unique >= TARGET_PER_CLASS and sp_unique >= TARGET_PER_CLASS
            target_bf = TARGET_PER_CLASS if eligible else min(TARGET_PER_CLASS, bf_unique)
            target_sp = TARGET_PER_CLASS if eligible else min(TARGET_PER_CLASS, sp_unique)
            max_units = (target_bf + target_sp) * (1 + 4)
            rows.append(
                {
                    "dataset": dataset,
                    "generator": generator,
                    "bf_unique": bf_unique,
                    "sp_unique": sp_unique,
                    "bf_access_sample_frac": round(bf_access, 3),
                    "sp_access_sample_frac": round(sp_access, 3),
                    "eligible_500": eligible,
                    "target_bf_orig": target_bf,
                    "target_sp_orig": target_sp,
                    "max_achievable_units": max_units,
                }
            )

    out_csv = out_dir / "protocol_pool_audit.csv"
    pd.DataFrame(rows).to_csv(out_csv, index=False)

    eligible_n = sum(1 for r in rows if r["eligible_500"])
    summary = {
        "protocol_csv": str(protocol_csv),
        "generators_total": len(rows),
        "eligible_500": eligible_n,
        "ineligible": [f"{r['dataset']}/{r['generator']}" for r in rows if not r["eligible_500"]],
        "target_per_eligible_generator": UNITS_PER_ELIGIBLE_GENERATOR,
        "detail_csv": str(out_csv),
    }
    (out_dir / "protocol_pool_audit.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"Wrote {out_csv}")


if __name__ == "__main__":
    main()
