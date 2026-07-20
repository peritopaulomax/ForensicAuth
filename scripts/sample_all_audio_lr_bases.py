#!/usr/bin/env python3
"""Sample 500 bonafide + 500 spoof per generator for all audio LR reference bases."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src" / "backend"))

import pandas as pd

from audio_lr_dataset_utils import (
    build_manifest_rows,
    filter_min_duration,
    infer_generator,
    label_to_y_spoof,
    load_config,
    reset_dir,
    sample_generator_balanced,
    write_json,
    write_manifest,
)
from core.audio_spoofing_lr_reference import REFERENCE_GENERATORS

PER_CLASS_DEFAULT = 500


def load_protocol_filtered(protocol_csv: Path, datasets: set[str]) -> pd.DataFrame:
    chunks: list[pd.DataFrame] = []
    for chunk in pd.read_csv(protocol_csv, chunksize=200_000):
        chunk = chunk[chunk["status"].fillna("").eq("ok")].copy()
        chunk = chunk[chunk["dataset"].isin(datasets)].copy()
        if chunk.empty:
            continue
        chunk["generator"] = chunk.apply(lambda row: infer_generator(row.to_dict()), axis=1)
        chunk["y_spoof"] = chunk["label"].map(label_to_y_spoof).astype(int)
        chunks.append(chunk)
    if not chunks:
        raise RuntimeError("Nenhuma linha encontrada nos datasets selecionados")
    return pd.concat(chunks, ignore_index=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/audio_lr_protocolo.yaml")
    parser.add_argument("--protocol-csv", default="protocolo_unificado.csv")
    parser.add_argument("--per-class", type=int, default=PER_CLASS_DEFAULT)
    parser.add_argument("--seed", type=int, default=20260705)
    parser.add_argument("--out-dir", default="outputs/lr_calibration/audio_spoofing/samples/full")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--estimate-only", action="store_true")
    args = parser.parse_args()

    config = load_config(ROOT / args.config)
    per_class = args.per_class or int(config.get("poc", {}).get("sample_per_class", PER_CLASS_DEFAULT))

    generators: list[tuple[str, str]] = []
    for dataset, gens in REFERENCE_GENERATORS.items():
        for gen in gens:
            generators.append((dataset, gen))

    n_gens = len(generators)
    n_files = n_gens * per_class * 2
    est_sec_opt = n_files * 0.35
    est_sec_pes = n_files * 0.55

    print("=== Estimativa de tempo (score matrix, 3 detectores) ===")
    print(f"Geradores: {n_gens}")
    print(f"Amostras: {per_class} bonafide + {per_class} spoof × {n_gens} = {n_files:,} arquivos")
    print(f"Otimista (~0,35 s/arquivo): {est_sec_opt/3600:.1f} h ({est_sec_opt/60:.0f} min)")
    print(f"Conservador (~0,55 s/arquivo): {est_sec_pes/3600:.1f} h ({est_sec_pes/60:.0f} min)")
    print("CodecFake C1–C7 = 7 condições de codec neural distintas (não geradores TTS).\n")

    if args.estimate_only:
        return

    protocol_csv = ROOT / args.protocol_csv
    datasets = set(REFERENCE_GENERATORS.keys())
    t0 = time.time()
    print("Carregando protocolo filtrado…")
    df = load_protocol_filtered(protocol_csv, datasets)
    print(f"  {len(df):,} linhas em {time.time()-t0:.0f}s")
    # Filtro de duracao e aplicado implicitamente na score matrix; pools grandes evitam scan global lento.

    out_dir = ROOT / args.out_dir
    reset_dir(out_dir, args.force)

    sampled_parts: list[pd.DataFrame] = []
    report_rows: list[dict] = []
    seed = args.seed

    for idx, (dataset, generator) in enumerate(generators):
        try:
            part = sample_generator_balanced(
                df,
                dataset=dataset,
                generator=generator,
                per_class=per_class,
                seed=seed + idx,
            )
            part["purpose"] = "reference_population"
            part["reference_split"] = "reference_population"
            part["generator"] = generator
            sampled_parts.append(part)
            report_rows.append(
                {
                    "dataset": dataset,
                    "generator": generator,
                    "bonafide": per_class,
                    "spoof": per_class,
                    "status": "ok",
                }
            )
            print(f"  OK {dataset}/{generator}: {per_class}+{per_class}")
        except Exception as exc:
            report_rows.append(
                {
                    "dataset": dataset,
                    "generator": generator,
                    "status": "error",
                    "error": str(exc),
                }
            )
            print(f"  ERRO {dataset}/{generator}: {exc}")

    sampled = pd.concat(sampled_parts, ignore_index=True)
    manifest_rows = build_manifest_rows(sampled, config, copy_files=False, out_dir=out_dir)
    manifest_path = out_dir / "manifest.csv"
    write_manifest(manifest_path, manifest_rows)

    summary = {
        "generators_requested": n_gens,
        "generators_sampled": len(report_rows) - sum(1 for r in report_rows if r.get("status") == "error"),
        "per_class": per_class,
        "total_rows": len(manifest_rows),
        "bonafide": sum(1 for r in manifest_rows if int(r["y_spoof"]) == 0),
        "spoof": sum(1 for r in manifest_rows if int(r["y_spoof"]) == 1),
        "manifest": str(manifest_path),
        "elapsed_seconds": round(time.time() - t0, 1),
        "generators": report_rows,
        "score_matrix_estimate_hours": [est_sec_opt / 3600, est_sec_pes / 3600],
    }
    write_json(out_dir / "sampling_report.json", summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
