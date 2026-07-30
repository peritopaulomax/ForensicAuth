#!/usr/bin/env python3
"""Download TruVIL weights (TruVIL_train_VI_OP.pth) into models/truvil/weights/."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

GDRIVE_FILE_ID = "1eIttOWmFopKKGFyEN5yaUJfdZeg2nfDu"
WEIGHT_NAME = "TruVIL_train_VI_OP.pth"


def main() -> int:
    parser = argparse.ArgumentParser(description="Download TruVIL VI+OP weights")
    parser.add_argument(
        "--dest-dir",
        type=Path,
        default=None,
        help="Destination weights dir (default: <repo>/models/truvil/weights)",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    dest_dir = args.dest_dir or (root / "models" / "truvil" / "weights")
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / WEIGHT_NAME

    if dest.is_file() and dest.stat().st_size > 1_000_000:
        print(f"Ja existe: {dest} ({dest.stat().st_size} bytes)")
        return 0

    try:
        import gdown
    except ImportError:
        print("Instale gdown: pip install gdown", file=sys.stderr)
        return 1

    url = f"https://drive.google.com/uc?id={GDRIVE_FILE_ID}"
    print(f"Baixando TruVIL weights → {dest}")
    print(f"Fonte: {url}")
    print("Vendor: git clone https://github.com/multimediaFor/TruVIL vendor/truvil")
    gdown.download(url, str(dest), quiet=False)
    if not dest.is_file() or dest.stat().st_size < 1_000_000:
        print("Falha no download.", file=sys.stderr)
        return 1
    print(f"OK: {dest} ({dest.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
