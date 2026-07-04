#!/usr/bin/env python3
"""Baixa/copia assets oficiais CLIDE e cache OpenAI CLIP ViT-L/14."""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "vendor" / "clide"
TARGET = ROOT / "models" / "clide"
ASSETS = [
    "rep_matrix_general.pt",
    "rep_matrix_cars.pt",
    "whitening_matrix_general.pt",
    "whitening_matrix_cars.pt",
]


def _copy_assets() -> None:
    TARGET.mkdir(parents=True, exist_ok=True)
    for name in ASSETS:
        src = VENDOR / name
        dest = TARGET / name
        if dest.is_file() and dest.stat().st_size > 1_000:
            print(f"OK  {dest} ({dest.stat().st_size} bytes)")
            continue
        if not src.is_file():
            raise SystemExit(f"Asset CLIDE ausente no vendor: {src}")
        shutil.copy2(src, dest)
        print(f"OK  {dest} ({dest.stat().st_size} bytes)")


def _download_clip() -> None:
    try:
        from clip.clip import _MODELS, _download
    except ImportError as exc:
        raise SystemExit("Instale OpenAI CLIP antes de baixar o peso ViT-L/14.") from exc

    cache = TARGET / "clip"
    cache.mkdir(parents=True, exist_ok=True)
    path = _download(_MODELS["ViT-L/14"], str(cache))
    print(f"OK  CLIP ViT-L/14: {path}")


def main() -> None:
    _copy_assets()
    _download_clip()


if __name__ == "__main__":
    main()
