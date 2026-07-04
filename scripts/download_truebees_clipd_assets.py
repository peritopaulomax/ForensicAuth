#!/usr/bin/env python3
"""Baixa/prepara os pesos oficiais GRIP CLIP-D.

O nome do script foi preservado por compatibilidade com mensagens antigas, mas
agora segue o repositório oficial do artigo:
https://github.com/grip-unina/ClipBased-SyntheticImageDetection
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "vendor" / "grip_clipbased_synthetic"
TARGET = ROOT / "models" / "grip_clipd" / "weights"
REPO = "https://github.com/grip-unina/ClipBased-SyntheticImageDetection"
MODEL_NAMES = ("clipdet_latent10k", "clipdet_latent10k_plus", "Corvi2023")


def main() -> None:
    _ensure_vendor()
    _copy_weights()
    _cache_openclip_backbone()


def _run(cmd: list[str], cwd: Path | None = None) -> None:
    subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=True)


def _ensure_vendor() -> None:
    if not VENDOR.is_dir():
        VENDOR.parent.mkdir(parents=True, exist_ok=True)
        _run(["git", "clone", REPO, str(VENDOR)])
    _run(["git", "lfs", "install"], cwd=VENDOR)
    _run(["git", "lfs", "pull"], cwd=VENDOR)
    _run(["git", "lfs", "checkout"], cwd=VENDOR)


def _copy_weights() -> None:
    TARGET.mkdir(parents=True, exist_ok=True)
    for model_name in MODEL_NAMES:
        src_dir = VENDOR / "weights" / model_name
        dest_dir = TARGET / model_name
        dest_dir.mkdir(parents=True, exist_ok=True)
        for name in ("config.yaml", "weights.pth"):
            src = src_dir / name
            dest = dest_dir / name
            if not src.is_file() or src.stat().st_size < 1_000 and name == "weights.pth":
                raise SystemExit(f"Asset GRIP CLIP-D invalido ou ausente: {src}")
            shutil.copy2(src, dest)
            print(f"OK  {dest} ({dest.stat().st_size} bytes)")


def _cache_openclip_backbone() -> None:
    try:
        import open_clip
        from huggingface_hub import hf_hub_download
    except ImportError as exc:
        raise SystemExit("Instale open-clip-torch para preparar o backbone do CLIP-D.") from exc

    weights = hf_hub_download("laion/CLIP-ViT-L-14-CommonPool.XL-s13B-b90K", "open_clip_pytorch_model.bin")
    open_clip.create_model(
        "ViT-L-14",
        pretrained=weights,
    )
    print("OK  OpenCLIP ViT-L/14 CommonPool em cache")


if __name__ == "__main__":
    main()

