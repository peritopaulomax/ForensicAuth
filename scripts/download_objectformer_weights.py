#!/usr/bin/env python3
"""Baixa pesos ObjectFormer (IMDL-BenCo reproduction, CVPR 2022).

Repositorio original: https://github.com/wdrink/Objectformer
Checkpoints IMDL-BenCo (Google Drive):
  https://drive.google.com/drive/folders/1DCqc016-N4YvoMKKA87bFtrCdPVIDxAp

Arquivos esperados em models/imdlbenco/objectformer/:
  - processed_model_weights.pth   (init ViT-B/16 processado — issue #41)
  - object_former_casiav2.pth     (checkpoint treinado CASIAv2, chave 'model')
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "models" / "imdlbenco" / "objectformer"
BUILD_INIT = ROOT / "scripts" / "build_objectformer_init.py"

GDRIVE_FOLDER_ID = "1DCqc016-N4YvoMKKA87bFtrCdPVIDxAp"
CHECKPOINT_NAME = "object_former_casiav2.pth"
GDRIVE_CHECKPOINT = "objectformer_casiav2.pth"
MIN_INIT_BYTES = 100_000_000
MIN_CHECKPOINT_BYTES = 100_000_000


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _validate_checkpoint(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size < MIN_CHECKPOINT_BYTES:
        return False
    try:
        import torch

        obj = torch.load(str(path), map_location="cpu", weights_only=False)
        if isinstance(obj, dict) and "model" in obj:
            print(f"OK  {path.name} ({path.stat().st_size // 1_000_000} MB, chave 'model')")
            return True
        print(f"AVISO  {path.name} sem chave 'model'")
    except Exception as exc:
        print(f"FALHA  {path.name}: {exc}")
    return False


def _ensure_init_weights(dest: Path) -> bool:
    if dest.is_file() and dest.stat().st_size >= MIN_INIT_BYTES:
        print(f"OK  {dest.name}")
        return True
    print("Gerando processed_model_weights.pth (timm ViT-B/16)...")
    try:
        spec = importlib.util.spec_from_file_location("build_objectformer_init", BUILD_INIT)
        if spec is None or spec.loader is None:
            raise RuntimeError("build_objectformer_init.py ausente")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.build_processed_weights(dest)
        ok = dest.is_file() and dest.stat().st_size >= MIN_INIT_BYTES
        print("OK" if ok else "FALHA", dest)
        return ok
    except Exception as exc:
        print(f"FALHA  init ObjectFormer: {exc}")
        return False


def _publish_checkpoint(src: Path, dest: Path) -> None:
    if dest.resolve() == src.resolve():
        return
    if dest.is_symlink() or dest.is_file():
        dest.unlink(missing_ok=True)
    try:
        dest.symlink_to(src.relative_to(dest.parent))
    except OSError:
        shutil.copy2(src, dest)
    print(f"OK  {dest.name} -> {src.name}")


def _try_gdown_checkpoint(staging: Path) -> Path | None:
    try:
        import gdown
    except ImportError:
        print("gdown ausente — pip install gdown")
        return None

    canonical = staging / GDRIVE_CHECKPOINT
    if _validate_checkpoint(canonical):
        return canonical

    print("Baixando IMDLBenCo_ckpt (Google Drive, pode demorar)...")
    gdown.download_folder(
        id=GDRIVE_FOLDER_ID,
        output=str(staging),
        quiet=False,
        use_cookies=False,
    )
    if _validate_checkpoint(canonical):
        return canonical
    for p in staging.rglob(GDRIVE_CHECKPOINT):
        if _validate_checkpoint(p):
            return p
    return None


def main() -> int:
    base = Path(os.environ.get("IMDLBENCO_MODELS_DIR", ROOT / "models" / "imdlbenco")).resolve()
    target = _ensure_dir(base / "objectformer")
    print(f"Destino: {target}\n")

    init_path = target / "processed_model_weights.pth"
    if not _ensure_init_weights(init_path):
        return 1

    ckpt_path = target / CHECKPOINT_NAME
    if _validate_checkpoint(ckpt_path):
        print("\nObjectFormer: todos os pesos presentes.")
        return 0

    staging = target / "_gdrive"
    downloaded = _try_gdown_checkpoint(staging)
    if downloaded is None:
        print("\n=== Download manual ===")
        print("Google Drive IMDLBenCo_ckpt:")
        print("  https://drive.google.com/drive/folders/1DCqc016-N4YvoMKKA87bFtrCdPVIDxAp")
        print(f"Copie objectformer_casiav2.pth para {ckpt_path}")
        print("Baidu (alternativa): https://pan.baidu.com/s/1DtkOwLCTunvI3d_GAAj2Dg (codigo: bchm)")
        return 1

    _publish_checkpoint(downloaded, ckpt_path)
    print("\nObjectFormer: todos os pesos presentes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
