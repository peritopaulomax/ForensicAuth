#!/usr/bin/env python3
"""Baixa pesos Effort (GenImage, Chameleon) e CLIP ViT-L/14."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "models" / "effort"

VARIANTS = {
    "effort_genimage_sdv14.pth": "1UXf1hC9FC1yV93uKwXSkdtepsgpIAU9d",
    "effort_chameleon_sdv14.pth": "1GlJ1y4xmTdqV0FfIcyBwNNU6cQird9DR",
}

CLIP_HF = "openai/clip-vit-large-patch14"
CLIP_DRIVE_FOLDER = "1fm3Jd8lFMiSP1qgdmsxfqlJZGpr_bXsx"


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _try_gdown(file_id: str, dest: Path) -> bool:
    if dest.is_file() and dest.stat().st_size > 100_000:
        print(f"OK  {dest.name}")
        return True
    try:
        import gdown
    except ImportError:
        return False
    try:
        gdown.download(id=file_id, output=str(dest), quiet=False)
        return dest.is_file() and dest.stat().st_size > 100_000
    except Exception as exc:
        print(f"gdown falhou ({dest.name}): {exc}")
        return False


def _download_clip_hf(dest: Path) -> bool:
    if (dest / "config.json").is_file():
        print(f"OK  {dest.name}")
        return True
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("FALHA  huggingface_hub ausente para CLIP")
        return False
    try:
        cached = snapshot_download(repo_id=CLIP_HF, local_dir=str(dest))
        ok = Path(cached, "config.json").is_file()
        print(f"{'OK' if ok else 'FALHA'}  {dest}")
        return ok
    except Exception as exc:
        print(f"FALHA  CLIP HF: {exc}")
        return False


def main() -> None:
    base = Path(os.environ.get("EFFORT_MODELS_DIR", TARGET)).resolve()
    print(f"Destino: {base}")
    _ensure_dir(base)

    print("--- Effort checkpoints (Google Drive) ---")
    for fname, drive_id in VARIANTS.items():
        dest = base / fname
        if not _try_gdown(drive_id, dest):
            print(f"PENDENTE  {fname}")
            print(f"  https://drive.google.com/file/d/{drive_id}/view")

    print("--- CLIP ViT-L/14 ---")
    clip_dir = base / "clip-vit-large-patch14"
    if not _download_clip_hf(clip_dir):
        tmp = base / "_clip_drive_tmp"
        try:
            import gdown

            shutil.rmtree(tmp, ignore_errors=True)
            gdown.download_folder(
                id=CLIP_DRIVE_FOLDER,
                output=str(tmp),
                quiet=False,
                use_cookies=False,
            )
            found = list(tmp.rglob("config.json"))
            if found:
                src_root = found[0].parent
                if clip_dir.exists():
                    shutil.rmtree(clip_dir)
                shutil.copytree(src_root, clip_dir)
                print(f"OK  {clip_dir.name} (Drive)")
            else:
                print("PENDENTE  CLIP — use HF ou Drive oficial Effort")
        except Exception as exc:
            print(f"PENDENTE  CLIP: {exc}")

    shutil.rmtree(base / "_clip_drive_tmp", ignore_errors=True)
    print("Download Effort concluido (verifique itens PENDENTE).")


if __name__ == "__main__":
    main()
