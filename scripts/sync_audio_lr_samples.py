#!/usr/bin/env python3
"""Sync/copy audio LR sample files from LAN-mounted bases into local samples_root."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
from pathlib import Path

from audio_lr_dataset_utils import (
    load_config,
    manifest_input_path,
    read_manifest,
    resolve_audio_path,
    safe_name,
    sha256_file,
    write_json,
    write_manifest,
)


def _rsync(source: Path, dest: Path, *, dry_run: bool) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["rsync", "-a", "--info=progress2"]
    if dry_run:
        cmd.append("--dry-run")
    cmd.extend([str(source), str(dest)])
    subprocess.run(cmd, check=True)


def _materialize_row(row: dict[str, str], out_root: Path) -> dict[str, str]:
    source = Path(row["resolved_path"] or resolve_audio_path(row["source_path"], {}))
    if not source.exists():
        row = dict(row)
        row["sync_status"] = "missing"
        return row
    suffix = source.suffix.lower() or ".wav"
    digest = sha256_file(source)
    filename = f"{safe_name(row.get('source_id') or source.stem)}__{digest[:12]}{suffix}"
    dest_relative = (
        Path(str(row.get("purpose", "calibration_train")))
        / safe_name(str(row.get("dataset", "unknown")))
        / safe_name(str(row.get("generator", "unknown")))
        / safe_name(str(row.get("label_name") or row.get("label", "unknown")))
        / filename
    ).as_posix()
    dest = out_root / dest_relative
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        shutil.copy2(source, dest)
    updated = dict(row)
    updated["dest_relative"] = dest_relative
    updated["sha256"] = digest
    updated["bytes"] = str(dest.stat().st_size)
    updated["sync_status"] = "copied"
    return updated


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--config", default="")
    parser.add_argument("--out-dir", default="")
    parser.add_argument("--method", choices=("copy", "rsync"), default="copy")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()

    config = load_config(Path(args.config) if args.config else None)
    manifest_path = Path(args.manifest)
    rows = read_manifest(manifest_path)
    out_root = Path(args.out_dir or manifest_path.parent)
    if not out_root.is_absolute():
        out_root = Path(__file__).resolve().parents[1] / out_root

    updated_rows: list[dict[str, str]] = []
    copied = 0
    missing = 0
    for row in rows:
        resolved = resolve_audio_path(str(row.get("source_path", "")), config)
        row = dict(row)
        row["resolved_path"] = str(resolved)
        if args.check_only:
            row["sync_status"] = "accessible" if resolved.exists() else "missing"
            updated_rows.append(row)
            if resolved.exists():
                copied += 1
            else:
                missing += 1
            continue
        if not resolved.exists():
            row["sync_status"] = "missing"
            missing += 1
            updated_rows.append(row)
            continue
        if args.method == "rsync":
            dest = out_root / Path(str(row.get("dest_relative") or resolved.name))
            if args.dry_run:
                print(f"DRY rsync {resolved} -> {dest}")
            else:
                _rsync(resolved, dest, dry_run=False)
            row["dest_relative"] = dest.relative_to(out_root).as_posix()
            row["sync_status"] = "rsynced"
            copied += 1
            updated_rows.append(row)
        else:
            updated_rows.append(_materialize_row(row, out_root))
            copied += 1

    if not args.dry_run and not args.check_only:
        write_manifest(out_root / "manifest.csv", updated_rows)

    report = {
        "manifest": str(manifest_path),
        "out_dir": str(out_root),
        "rows": len(rows),
        "copied_or_accessible": copied,
        "missing": missing,
        "method": args.method,
        "dry_run": args.dry_run,
        "check_only": args.check_only,
    }
    write_json(out_root / "sync_report.json", report)
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
