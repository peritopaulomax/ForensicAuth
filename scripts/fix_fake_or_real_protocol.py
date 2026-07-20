#!/usr/bin/env python3
"""Rebuild Fake-or-Real rows in protocolo_unificado.csv from for-norm/testing folders.

The unified protocol incorrectly mapped both bonafide and spoof labels to files
under ``testing/fake/``.  Ground truth follows the directory layout:

- ``testing/real/``  -> bonafide
- ``testing/fake/``  -> spoof
"""

from __future__ import annotations

import argparse
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from audio_lr_dataset_utils import load_config

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROTOCOL = PROJECT_ROOT / "protocolo_unificado.csv"
DATASET_NAME = "Fake-or-Real"
FOR_NORM_REL = "Speech_DF_Arena/AntiSpoofing-Datasets/for-norm/testing"


def _remote_prefix(config: dict) -> str:
    for mapping in config.get("path_prefixes") or []:
        remote = str(mapping.get("remote", "")).rstrip("/")
        if remote:
            return remote
    return "/media/paulopmgir/HD10T-Bases"


def _local_prefix(config: dict) -> str:
    for mapping in config.get("path_prefixes") or []:
        local = str(mapping.get("local", "")).rstrip("/")
        if local:
            return local
    return "/mnt/bases"


def build_fake_or_real_rows(
    *,
    local_bases_root: Path,
    remote_bases_root: str,
) -> pd.DataFrame:
    testing_root = local_bases_root / FOR_NORM_REL
    real_dir = testing_root / "real"
    fake_dir = testing_root / "fake"
    if not real_dir.is_dir():
        raise FileNotFoundError(f"Pasta real ausente: {real_dir}")
    if not fake_dir.is_dir():
        raise FileNotFoundError(f"Pasta fake ausente: {fake_dir}")

    remote_prefix = remote_bases_root.rstrip("/")
    rows: list[dict[str, str]] = []

    for label, folder in (("bonafide", "real"), ("spoof", "fake")):
        audio_dir = testing_root / folder
        for path in sorted(audio_dir.glob("*.wav")):
            rel = f"{FOR_NORM_REL}/{folder}/{path.name}"
            rows.append(
                {
                    "file_path": f"{remote_prefix}/{rel}",
                    "label": label,
                    "dataset": DATASET_NAME,
                    "subset": "",
                    "original_csv": "fake_or_real.csv",
                    "status": "ok",
                }
            )

    df = pd.DataFrame(rows)
    if df.empty:
        raise RuntimeError("Nenhum arquivo .wav encontrado em for-norm/testing")
    dup = df.groupby("file_path")["label"].nunique()
    conflicts = dup[dup > 1]
    if not conflicts.empty:
        raise RuntimeError(f"Paths com rótulos conflitantes: {len(conflicts)}")
    return df


def patch_protocol_csv(
    protocol_csv: Path,
    fixed_rows: pd.DataFrame,
    *,
    backup: bool = True,
) -> dict[str, int]:
    if not protocol_csv.is_file():
        raise FileNotFoundError(protocol_csv)

    if backup:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_path = protocol_csv.with_suffix(f".csv.bak-for-{stamp}")
        shutil.copy2(protocol_csv, backup_path)
        print(f"Backup: {backup_path}")

    print(f"Lendo {protocol_csv} …")
    df = pd.read_csv(protocol_csv, low_memory=False)
    before_for = int((df["dataset"] == DATASET_NAME).sum())
    kept = df[df["dataset"] != DATASET_NAME].copy()
    merged = pd.concat([kept, fixed_rows], ignore_index=True)
    merged.to_csv(protocol_csv, index=False)

    return {
        "rows_before": len(df),
        "fake_or_real_before": before_for,
        "fake_or_real_after": len(fixed_rows),
        "rows_after": len(merged),
    }


def write_standalone_csv(rows: pd.DataFrame, output_csv: Path) -> None:
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    rows.to_csv(output_csv, index=False)
    print(f"CSV standalone: {output_csv}")


def summarize_rows(rows: pd.DataFrame) -> None:
    print("\nResumo Fake-or-Real reconstruído:")
    print(rows["label"].value_counts().to_string())
    rows = rows.copy()
    rows["folder"] = rows["file_path"].str.extract(r"/for-norm/testing/([^/]+)/")
    print("\nPor pasta:")
    print(rows.groupby(["folder", "label"]).size().to_string())
    print(f"\nTotal: {len(rows)} linhas, {rows['file_path'].nunique()} paths únicos")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(PROJECT_ROOT / "config" / "audio_lr_protocolo.yaml"))
    parser.add_argument("--protocol-csv", default=str(DEFAULT_PROTOCOL))
    parser.add_argument(
        "--standalone-csv",
        default=str(PROJECT_ROOT / "config" / "protocols" / "fake_or_real_fixed.csv"),
        help="Grava CSV corrigido separado (file_path,label,...).",
    )
    parser.add_argument("--dry-run", action="store_true", help="Não altera protocolo_unificado.csv")
    parser.add_argument("--no-backup", action="store_true")
    args = parser.parse_args()

    config = load_config(Path(args.config))
    local_root = Path(_local_prefix(config))
    remote_root = _remote_prefix(config)

    fixed = build_fake_or_real_rows(
        local_bases_root=local_root,
        remote_bases_root=remote_root,
    )
    summarize_rows(fixed)
    write_standalone_csv(fixed, Path(args.standalone_csv))

    if args.dry_run:
        print("\n[dry-run] protocolo_unificado.csv não foi alterado.")
        return

    stats = patch_protocol_csv(
        Path(args.protocol_csv),
        fixed,
        backup=not args.no_backup,
    )
    print("\nProtocolo atualizado:")
    for key, value in stats.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
