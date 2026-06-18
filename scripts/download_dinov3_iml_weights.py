#!/usr/bin/env python3
"""Baixa codigo e pesos DINOv3-IML (ViT-L + LoRA r=32, protocolo CAT).

Repositorio: https://github.com/Irennnne/DINOv3-IML
Checkpoint oficial (Google Drive): pasta ViT-L LoRA r=32 — protocolo CAT-Net.

Arquivos esperados:
  vendor/DINOv3-IML/          — codigo do projeto
  vendor/dinov3/              — backbone Meta DINOv3 (torch.hub local)
  models/imdlbenco/dinov3_iml/cat_vitl_lora_r32.pth
    ou checkpoint-48.pth (mesmo conteudo, ~1.3 GB)
"""

from __future__ import annotations

import os
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDOR_IML = ROOT / "vendor" / "DINOv3-IML"
VENDOR_DINOV3 = ROOT / "vendor" / "dinov3"
TARGET = ROOT / "models" / "imdlbenco" / "dinov3_iml"

GDRIVE_FOLDER_ID = "125leLub_M-lICa1ILTOL-FCz4ZY6eutj"
MIN_CHECKPOINT_BYTES = 100_000_000


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _fetch_github_zip(url: str, dest: Path, glob_pattern: str) -> bool:
    if dest.is_dir():
        print(f"OK  {dest}")
        return True
    archive = dest.parent / f"_{dest.name}.zip"
    print(f"Baixando {url}...")
    urllib.request.urlretrieve(url, archive)
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(dest.parent)
    archive.unlink(missing_ok=True)
    if not dest.is_dir():
        for p in dest.parent.glob(glob_pattern):
            if p.is_dir():
                p.rename(dest)
                break
    ok = dest.is_dir()
    print("OK" if ok else "FALHA", dest)
    return ok


def _ensure_vendor() -> bool:
    ok_iml = _fetch_github_zip(
        "https://github.com/Irennnne/DINOv3-IML/archive/refs/heads/main.zip",
        VENDOR_IML,
        "DINOv3-IML-*",
    )
    ok_dino = _fetch_github_zip(
        "https://github.com/facebookresearch/dinov3/archive/refs/heads/main.zip",
        VENDOR_DINOV3,
        "dinov3-*",
    )
    return ok_iml and ok_dino


def _try_gdown_checkpoint() -> Path | None:
    try:
        import gdown
    except ImportError:
        print("gdown ausente — pip install gdown")
        return None

    staging = TARGET / "_gdrive"
    _ensure_dir(staging)
    existing = list(staging.glob("checkpoint-*.pth")) + list(TARGET.glob("checkpoint-*.pth"))
    for p in existing:
        if p.stat().st_size >= MIN_CHECKPOINT_BYTES:
            return p

    print("Baixando checkpoint ViT-L LoRA r=32 (Google Drive, ~1.3 GB)...")
    gdown.download_folder(
        id=GDRIVE_FOLDER_ID,
        output=str(staging),
        quiet=False,
        use_cookies=False,
    )
    candidates = sorted(staging.glob("checkpoint-*.pth"), key=lambda p: p.stat().st_size, reverse=True)
    for p in candidates:
        if p.stat().st_size >= MIN_CHECKPOINT_BYTES:
            return p
    return None


def _publish_checkpoint(src: Path) -> None:
    canonical = TARGET / "cat_vitl_lora_r32.pth"
    if canonical.resolve() == src.resolve():
        return
    if canonical.is_symlink() or canonical.is_file():
        canonical.unlink(missing_ok=True)
    try:
        canonical.symlink_to(src.relative_to(TARGET))
    except OSError:
        shutil.copy2(src, canonical)
    print(f"OK  {canonical} -> {src.name}")


def main() -> int:
    _ensure_dir(TARGET)
    if not _ensure_vendor():
        return 1

    ckpt = TARGET / "cat_vitl_lora_r32.pth"
    if ckpt.is_file() and ckpt.stat().st_size >= MIN_CHECKPOINT_BYTES:
        print(f"OK  checkpoint {ckpt.stat().st_size // 1_000_000} MB")
        return 0

    for p in sorted(TARGET.glob("checkpoint-*.pth"), reverse=True):
        if p.stat().st_size >= MIN_CHECKPOINT_BYTES:
            _publish_checkpoint(p)
            return 0

    downloaded = _try_gdown_checkpoint()
    if downloaded is None:
        print(
            "PENDENTE  checkpoint ViT-L LoRA r=32\n"
            "  Baixe manualmente de:\n"
            "  https://drive.google.com/drive/folders/125leLub_M-lICa1ILTOL-FCz4ZY6eutj\n"
            f"  Salve como {TARGET}/cat_vitl_lora_r32.pth ou checkpoint-48.pth"
        )
        return 1

    dest = TARGET / downloaded.name
    if downloaded.resolve() != dest.resolve():
        shutil.copy2(downloaded, dest)
    _publish_checkpoint(dest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
