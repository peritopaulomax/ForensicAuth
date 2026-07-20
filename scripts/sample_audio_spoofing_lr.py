#!/usr/bin/env python3
"""Sample balanced bonafide/spoof audio rows from protocolo_unificado.csv for LR calibration."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from audio_lr_dataset_utils import (
    assign_purpose_splits,
    build_manifest_rows,
    filter_min_duration,
    iter_accessible,
    load_config,
    protocol_summary,
    read_protocol_csv,
    reset_dir,
    sample_balanced,
    write_json,
    write_manifest,
)


def _parse_subset_specs(values: list[str]) -> list[tuple[str, str]]:
    specs: list[tuple[str, str]] = []
    for value in values:
        if "/" not in value:
            raise ValueError(f"Formato esperado dataset/subset, recebido: {value!r}")
        dataset, subset = value.split("/", 1)
        specs.append((dataset.strip(), subset.strip()))
    return specs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="", help="YAML config (default: config/audio_lr_protocolo.yaml)")
    parser.add_argument("--protocol-csv", default="", help="Override protocol CSV path")
    parser.add_argument("--subset", action="append", default=[], help="dataset/subset (repeatable)")
    parser.add_argument("--per-class", type=int, default=0, help="Samples per class per generator")
    parser.add_argument("--with-splits", action="store_true", help="Assign train/calib/test purposes")
    parser.add_argument("--train-per-class", type=int, default=0)
    parser.add_argument("--calib-per-class", type=int, default=0)
    parser.add_argument("--test-per-class", type=int, default=0)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out-dir", default="", help="Output directory for manifest")
    parser.add_argument("--copy-files", action="store_true", help="Copy audio files locally when accessible")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--summary-only", action="store_true")
    args = parser.parse_args()

    config = load_config(Path(args.config) if args.config else None)
    protocol_csv = Path(args.protocol_csv or config.get("protocol_csv", "protocolo_unificado.csv"))
    if not protocol_csv.is_absolute():
        protocol_csv = Path(__file__).resolve().parents[1] / protocol_csv

    if args.summary_only:
        summary = protocol_summary(protocol_csv)
        print(summary.to_string(index=False))
        return

    subset_specs = _parse_subset_specs(args.subset)
    if not subset_specs:
        defaults = config.get("poc_defaults") or []
        subset_specs = [(item["dataset"], item["subset"]) for item in defaults[:1]]
    datasets = sorted({dataset for dataset, _ in subset_specs})
    subsets = sorted({subset for _, subset in subset_specs})

    poc = config.get("poc") or {}
    per_class = args.per_class or int(poc.get("sample_per_class", 150))
    seed = args.seed or int(poc.get("seed", 20260704))
    train_per_class = args.train_per_class or int(poc.get("train_per_class", 75))
    calib_per_class = args.calib_per_class or int(poc.get("calib_per_class", 38))
    test_per_class = args.test_per_class or int(poc.get("test_per_class", 37))

    df = read_protocol_csv(protocol_csv, datasets=datasets, subsets=subsets)
    mask = df.apply(lambda row: (row["dataset"], row["subset"]) in subset_specs, axis=1)
    df = df[mask].copy()
    if df.empty:
        raise RuntimeError(f"Nenhuma linha encontrada para subsets={subset_specs}")

    before_duration = len(df)
    df = filter_min_duration(df, config)
    if df.empty:
        raise RuntimeError(
            "Nenhum audio atende min_duration_seconds apos filtro. "
            "Verifique montagem LAN ou reduza o limiar."
        )

    if args.with_splits:
        total_per_class = train_per_class + calib_per_class + test_per_class
        sampled = sample_balanced(df, per_class=total_per_class, seed=seed)
        sampled = assign_purpose_splits(
            sampled,
            train_per_class=train_per_class,
            calib_per_class=calib_per_class,
            test_per_class=test_per_class,
            seed=seed,
        )
    else:
        sampled = sample_balanced(df, per_class=per_class, seed=seed)
        sampled["purpose"] = "calibration_train"
        sampled["reference_split"] = "calibration_train"
        sampled["label_name"] = sampled["label"]

    out_root = Path(args.out_dir or config.get("samples_root", "outputs/lr_calibration/audio_spoofing/samples"))
    if not out_root.is_absolute():
        out_root = Path(__file__).resolve().parents[1] / out_root
    reset_dir(out_root, args.force)

    manifest_rows = build_manifest_rows(sampled, config, copy_files=args.copy_files, out_dir=out_root)
    manifest_path = out_root / "manifest.csv"
    write_manifest(manifest_path, manifest_rows)

    accessible, missing = iter_accessible(manifest_rows, config)
    report = {
        "protocol_csv": str(protocol_csv),
        "subset_specs": subset_specs,
        "rows": len(manifest_rows),
        "bonafide": sum(1 for row in manifest_rows if int(row["y_spoof"]) == 0),
        "spoof": sum(1 for row in manifest_rows if int(row["y_spoof"]) == 1),
        "min_duration_seconds": config.get("min_duration_seconds", 0),
        "rows_after_duration_filter": len(df),
        "rows_before_duration_filter": before_duration,
        "accessible": len(accessible),
        "missing": len(missing),
        "copy_files": bool(args.copy_files),
        "manifest": str(manifest_path),
        "with_splits": bool(args.with_splits),
        "per_class": per_class if not args.with_splits else total_per_class,
        "seed": seed,
    }
    write_json(out_root / "sampling_report.json", report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if missing and not args.copy_files:
        print(
            f"\nAviso: {len(missing)} arquivos ainda inacessíveis nesta máquina. "
            "Use scripts/sync_audio_lr_samples.py quando a base estiver montada na LAN."
        )


if __name__ == "__main__":
    main()
