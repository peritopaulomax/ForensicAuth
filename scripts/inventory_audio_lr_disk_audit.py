#!/usr/bin/env python3
"""Disk-only audit wrapper — delegates to audio_lr_disk_verify."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src" / "backend"))

from audio_lr_disk_verify import TARGET_PER_CLASS, TARGET_AUG_PER_CLASS, audit_to_row, run_disk_audit  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default="outputs/lr_calibration/audio_spoofing/inventory")
    parser.add_argument("--protocol-audit", default="outputs/lr_calibration/audio_spoofing/inventory/protocol_pool_audit.csv")
    args = parser.parse_args()

    base = ROOT / "outputs/lr_calibration/audio_spoofing"
    protocol_audit = ROOT / args.protocol_audit

    print("Running disk audit...", flush=True)
    audits, summary = run_disk_audit(base_dir=base, protocol_audit_csv=protocol_audit)

    out_dir = ROOT / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame([audit_to_row(a) for a in audits])
    detail = out_dir / "disk_audit_by_generator.csv"
    df.to_csv(detail, index=False)

    summary_out = {
        **summary,
        "method": "filesystem_walk + score_matrix_audio_verify + scores_sidecar_or_csv",
        "targets": {
            "per_class_orig": TARGET_PER_CLASS,
            "per_class_aug": TARGET_AUG_PER_CLASS,
        },
        "detail_csv": str(detail),
    }
    (out_dir / "disk_audit_summary.json").write_text(json.dumps(summary_out, indent=2), encoding="utf-8")
    print(json.dumps(summary_out, indent=2))
    print(f"\nWrote {detail}")


if __name__ == "__main__":
    main()
