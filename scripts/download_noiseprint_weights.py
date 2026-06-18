#!/usr/bin/env python3
"""Baixa pesos Noiseprint para models/noiseprint/pretrained_weights/."""

from __future__ import annotations

import os
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "models" / "noiseprint" / "pretrained_weights"
BASE_URL = "https://raw.githubusercontent.com/RonyAbecidan/noiseprint-pytorch/main/pretrained_weights"

# Todos os pesos do repositorio upstream (QF 51-101)
DEFAULT_QFS = list(range(51, 102))


def _download_one(dest: Path, qf: int) -> None:
    name = f"model_qf{qf}.pth"
    out = dest / name
    if out.is_file() and out.stat().st_size > 100_000:
        print(f"OK  {name}")
        return
    url = f"{BASE_URL}/{name}"
    print(f"Baixando {name} ...")
    urllib.request.urlretrieve(url, out)
    if not out.is_file() or out.stat().st_size < 100_000:
        raise RuntimeError(f"Download invalido: {name}")
    print(f"OK  {name} ({out.stat().st_size // 1000} KB)")


def main() -> None:
    dest = Path(os.environ.get("NOISEPRINT_MODELS_DIR", TARGET.parent)).resolve()
    weights_dir = dest / "pretrained_weights"
    weights_dir.mkdir(parents=True, exist_ok=True)
    print(f"Destino: {weights_dir}")

    qfs = DEFAULT_QFS
    env = os.environ.get("NOISEPRINT_QFS")
    if env:
        qfs = [int(x.strip()) for x in env.split(",") if x.strip()]

    for qf in qfs:
        _download_one(weights_dir, qf)

    print("Pesos Noiseprint prontos.")


if __name__ == "__main__":
    main()
