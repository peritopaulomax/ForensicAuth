#!/usr/bin/env python3
"""Baixa checkpoint SAFE (checkpoint-best.pth) do repositorio oficial."""

from __future__ import annotations

import os
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "models" / "safe"
CHECKPOINT = "checkpoint-best.pth"
URL = "https://github.com/Ouxiang-Li/SAFE/raw/main/checkpoint/checkpoint-best.pth"


def main() -> None:
    dest_dir = Path(os.environ.get("SAFE_MODELS_DIR", TARGET)).resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / CHECKPOINT

    if dest.is_file() and dest.stat().st_size > 100_000:
        print(f"OK  {dest} ({dest.stat().st_size} bytes)")
        return

    print(f"Baixando SAFE de {URL}")
    print(f"Destino: {dest}")
    urllib.request.urlretrieve(URL, dest)
    if dest.is_file() and dest.stat().st_size > 100_000:
        print(f"OK  {dest} ({dest.stat().st_size} bytes)")
    else:
        print(f"FALHA  download incompleto: {dest}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
