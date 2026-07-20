#!/usr/bin/env python3
"""End-to-end POC driver for audio spoofing LR calibration."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def _run(cmd: list[str]) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subset", default="CodecFake/C1")
    parser.add_argument("--config", default="")
    parser.add_argument("--skip-sample", action="store_true")
    parser.add_argument("--skip-sync", action="store_true")
    parser.add_argument("--skip-scores", action="store_true")
    parser.add_argument("--skip-calibration", action="store_true")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    dataset, subset = args.subset.split("/", 1)
    out_dir = root / "outputs/lr_calibration/audio_spoofing/poc" / f"{dataset}_{subset}"
    manifest = out_dir / "manifest.csv"
    score_matrix = out_dir / "score_matrix.csv"
    calib_dir = out_dir / "calibration"

    py = sys.executable
    config_args = ["--config", args.config] if args.config else []

    if not args.skip_sample:
        _run(
            [
                py,
                str(root / "scripts/sample_audio_spoofing_lr.py"),
                *config_args,
                "--subset",
                f"{dataset}/{subset}",
                "--with-splits",
                "--out-dir",
                str(out_dir),
            ]
        )

    if not args.skip_sync:
        _run(
            [
                py,
                str(root / "scripts/sync_audio_lr_samples.py"),
                *config_args,
                "--manifest",
                str(manifest),
                "--out-dir",
                str(out_dir),
            ]
        )

    if not args.skip_scores:
        _run(
            [
                py,
                str(root / "scripts/run_audio_spoofing_score_matrix.py"),
                "--manifest",
                str(manifest),
                "--out",
                str(score_matrix),
                "--resume",
            ]
        )

    if not args.skip_calibration:
        _run(
            [
                py,
                str(root / "scripts/run_audio_bigaussianized_lr_poc.py"),
                "--score-matrix",
                str(score_matrix),
                "--out-dir",
                str(calib_dir),
            ]
        )

    print(json.dumps({"out_dir": str(out_dir), "manifest": str(manifest)}, indent=2))


if __name__ == "__main__":
    main()
