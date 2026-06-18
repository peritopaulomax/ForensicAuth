#!/usr/bin/env python3
"""Baixa pesos IAPL (ModelScope) e CLIP ViT-L/14.pt para deteccao de imagens sinteticas."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "models" / "iapl"
MODELSCOPE_ID = "yihengli/IAPL_pretrain"
CHECKPOINTS = ("checkpoint_best_acc_sd14.pth",)
CLIP_NAME = "ViT-L-14.pt"
OPEN_CLIP_MODEL = "ViT-L-14"
OPEN_CLIP_PRETRAINED = "openai"


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _export_clip_vit_l14(dest: Path) -> bool:
    if dest.is_file() and dest.stat().st_size > 1_000_000_000:
        print(f"OK  {dest.name} ({dest.stat().st_size} bytes)")
        return True
    try:
        import open_clip
        import torch
    except ImportError:
        print("FALHA  open_clip_torch ausente. pip install open_clip_torch")
        return False
    print(f"Exportando CLIP {OPEN_CLIP_MODEL} ({OPEN_CLIP_PRETRAINED}) → {dest.name} …")
    model, _, _ = open_clip.create_model_and_transforms(
        OPEN_CLIP_MODEL,
        pretrained=OPEN_CLIP_PRETRAINED,
    )
    torch.save(model.state_dict(), dest)
    ok = dest.is_file() and dest.stat().st_size > 1_000_000_000
    print(f"{'OK' if ok else 'FALHA'}  {dest}")
    return ok


def _download_modelscope(dest_dir: Path) -> bool:
    missing = [name for name in CHECKPOINTS if not (dest_dir / name).is_file()]
    if not missing:
        for name in CHECKPOINTS:
            p = dest_dir / name
            print(f"OK  {name} ({p.stat().st_size} bytes)")
        return True

    try:
        from modelscope import snapshot_download
    except ImportError:
        print("FALHA  modelscope ausente. pip install modelscope")
        return False

    print(f"Baixando IAPL de ModelScope ({MODELSCOPE_ID}) …")
    cache = snapshot_download(MODELSCOPE_ID)
    cache_path = Path(cache)
    ok_all = True
    for name in CHECKPOINTS:
        src = cache_path / name
        dest = dest_dir / name
        if not src.is_file():
            print(f"PENDENTE  {name} nao encontrado em {cache_path}")
            ok_all = False
            continue
        if not dest.is_file():
            shutil.copy2(src, dest)
        print(f"OK  {dest.name} ({dest.stat().st_size} bytes)")
    return ok_all


def main() -> None:
    dest_dir = _ensure_dir(Path(os.environ.get("IAPL_MODELS_DIR", TARGET)).resolve())
    print(f"Destino: {dest_dir}")

    print("--- CLIP ViT-L/14 ---")
    clip_ok = _export_clip_vit_l14(dest_dir / CLIP_NAME)

    print("--- Checkpoints IAPL (ModelScope) ---")
    ckpt_ok = _download_modelscope(dest_dir)

    if clip_ok and ckpt_ok:
        print("Download IAPL concluido.")
    else:
        print("Download IAPL incompleto — verifique rede e dependencias.")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
