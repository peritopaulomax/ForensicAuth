#!/usr/bin/env python3
"""End-to-end driver for latent typicality POC."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="experiments/poc_latent_typicality/config/poc_typicality.yaml")
    parser.add_argument("--skip-sample", action="store_true")
    parser.add_argument("--skip-extract", action="store_true")
    parser.add_argument("--skip-knn", action="store_true")
    parser.add_argument("--skip-experiments", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    py = sys.executable
    poc_dir = root / "experiments/poc_latent_typicality"

    if not args.skip_sample:
        run([py, str(poc_dir / "02_sample_poc_data.py"), "--config", args.config])

    extract_cmd = [py, str(poc_dir / "01_extract_scores_embeddings.py"), "--config", args.config, "--resume"]
    if args.limit > 0:
        extract_cmd.extend(["--limit", str(args.limit)])
    if not args.skip_extract:
        run(extract_cmd)

    if not args.skip_knn:
        run([py, str(poc_dir / "03_build_knn_reference.py"), "--config", args.config])

    if not args.skip_experiments:
        run([py, str(poc_dir / "05_run_experiments.py"), "--config", args.config])

    run([py, str(poc_dir / "08_generate_report.py"), "--config", args.config])


if __name__ == "__main__":
    main()
