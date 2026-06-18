#!/usr/bin/env python3
"""Baixa backbone SCNet e checkpoint STIL (se disponivel)."""

from __future__ import annotations

import os
import shutil
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "models" / "stil" / "weights"

SCNET_URL = "https://backseason.oss-cn-beijing.aliyuncs.com/scnet/scnet50_v1d-4109d1e1.pth"
SCNET_FILE = "scnet50_v1d.pth"
TRAINED_FILE = "stil_trained.pth"

# Checkpoint comunitario DeepfakeBench (FF++); substitua via STIL_WEIGHTS_PATH se necessario.
STIL_CANDIDATES = (
    "https://github.com/SCLBD/DeepfakeBench/releases/download/v1.0.1/stil_best.pth",
)


def _download(url: str, dest: Path) -> bool:
    if dest.is_file() and dest.stat().st_size > 100_000:
        print(f"OK  {dest.name}")
        return True
    print(f"Baixando {dest.name} de {url[:60]}…")
    tmp = dest.with_suffix(".part")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            data = resp.read()
    except Exception as exc:
        print(f"FALHA {dest.name}: {exc}")
        return False
    if len(data) < 100_000:
        print(f"FALHA {dest.name}: arquivo muito pequeno ({len(data)} bytes)")
        return False
    tmp.write_bytes(data)
    shutil.move(str(tmp), dest)
    print(f"OK  {dest} ({dest.stat().st_size} bytes)")
    return True


def main() -> None:
    dest = Path(os.environ.get("STIL_MODELS_DIR", TARGET.parent)).resolve() / "weights"
    dest.mkdir(parents=True, exist_ok=True)
    print(f"Destino: {dest}")

    ok = _download(SCNET_URL, dest / SCNET_FILE)
    trained = dest / TRAINED_FILE
    if not trained.is_file():
        for url in STIL_CANDIDATES:
            if _download(url, trained):
                break

    if not trained.is_file():
        print(
            "\nAVISO: checkpoint STIL treinado nao encontrado nos mirrors publicos.\n"
            "Treine via DeepfakeBench/TFace (FF++) e copie para:\n"
            f"  {trained}\n"
            "ou defina STIL_WEIGHTS_PATH apontando para o .pth treinado."
        )
        raise SystemExit(1 if not ok else 0)

    print("Download STIL concluido.")


if __name__ == "__main__":
    main()
