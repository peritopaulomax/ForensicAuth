#!/usr/bin/env python3
"""Baixa pesos oficiais do Forensic Self-Descriptions para cache local do projeto."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "vendor" / "fsd"
TARGET = ROOT / "models" / "fsd" / "weights"


def main() -> None:
    if not (VENDOR / "fsd" / "weights.py").is_file():
        raise SystemExit(f"Vendor FSD ausente: {VENDOR}")
    sys.path.insert(0, str(VENDOR))
    from fsd.weights import download_weights

    path = download_weights(dest=TARGET, attribution=False)
    print(f"OK  FSD: {path}")


if __name__ == "__main__":
    main()

