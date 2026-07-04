#!/usr/bin/env python3
"""Baixa DeeCLIP oficial: checkpoint Dropbox e cache CLIP ViT-L/14."""

from __future__ import annotations

import os
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "models" / "deeclip"
CHECKPOINT = "deeclip_weight_complete_with_lora_5.pth"
URL = (
    "https://www.dropbox.com/scl/fi/ttiqnbxu8atz4on5gqvgd/"
    "deeclip_weight_complete_with_lora_5.pth?rlkey=6xznuvriabkqfdcofhi1pbihu&st=fk02k7hf&dl=1"
)
CLIP_MODEL_ID = "openai/clip-vit-large-patch14"


def _download_checkpoint(dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and dest.stat().st_size > 100_000_000:
        print(f"OK  {dest} ({dest.stat().st_size} bytes)")
        return

    tmp = dest.with_suffix(dest.suffix + ".part")
    print(f"Baixando DeeCLIP de {URL}")
    print(f"Destino: {dest}")
    urllib.request.urlretrieve(URL, tmp)
    tmp.replace(dest)
    if dest.is_file() and dest.stat().st_size > 100_000_000:
        print(f"OK  {dest} ({dest.stat().st_size} bytes)")
    else:
        print(f"FALHA  download incompleto: {dest}")
        raise SystemExit(1)


def _download_clip(cache_dir: Path) -> None:
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise SystemExit("Instale huggingface_hub antes de baixar o cache CLIP.") from exc

    cache_dir.mkdir(parents=True, exist_ok=True)
    path = snapshot_download(
        CLIP_MODEL_ID,
        cache_dir=str(cache_dir),
        allow_patterns=[
            "config.json",
            "preprocessor_config.json",
            "model.safetensors",
            "pytorch_model.bin",
            "README.md",
        ],
    )
    print(f"OK  cache {CLIP_MODEL_ID}: {path}")


def main() -> None:
    target = Path(os.environ.get("DEECLIP_MODELS_DIR", TARGET)).resolve()
    checkpoint = target / "weights" / CHECKPOINT
    cache = Path(os.environ.get("DEECLIP_HF_CACHE", target / "huggingface")).resolve()
    _download_checkpoint(checkpoint)
    _download_clip(cache)


if __name__ == "__main__":
    main()
