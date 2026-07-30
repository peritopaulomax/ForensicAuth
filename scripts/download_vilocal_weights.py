#!/usr/bin/env python3
"""Ensure ViLocal weights (train_VI_OP.pth) are in models/vilocal/weights/."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

WEIGHT_NAME = "train_VI_OP.pth"


def main() -> int:
    parser = argparse.ArgumentParser(description="Install ViLocal train_VI_OP.pth weights")
    parser.add_argument("--dest-dir", type=Path, default=None)
    parser.add_argument(
        "--source",
        type=Path,
        default=None,
        help="Optional source .pth (default: vendor/vilocal/train_stage2/weights/train_VI_OP.pth)",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    dest_dir = args.dest_dir or (root / "models" / "vilocal" / "weights")
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / WEIGHT_NAME

    if dest.is_file() and dest.stat().st_size > 1_000_000:
        print(f"Ja existe: {dest} ({dest.stat().st_size} bytes)")
        return 0

    source = args.source or (root / "vendor" / "vilocal" / "train_stage2" / "weights" / WEIGHT_NAME)
    if source.is_file() and source.stat().st_size > 1_000_000:
        shutil.copy2(source, dest)
        print(f"OK (copiado do vendor): {dest} ({dest.stat().st_size} bytes)")
        return 0

    print(
        "Checkpoint ausente. Baixe train_VI_OP.pth (README ViLocal) e coloque em:\n"
        f"  {dest}\n"
        "ou clone o vendor com pesos em vendor/vilocal/train_stage2/weights/\n"
        "Fonte paper: https://github.com/multimediaFor/ViLocal",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
