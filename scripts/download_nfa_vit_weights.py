#!/usr/bin/env python3
"""Baixa ou valida pesos NFA-ViT (BR-Gen / model_zoo/nfa_vit).

Pesos oficiais (init + checkpoint treinado em BR-Gen):
  https://pan.baidu.com/s/1mqmMeoTzJf0TuIy17N6PFQ  (senha: cclp)

Arquivos esperados em models/imdlbenco/nfa_vit/:
  - noiseprint.pth                      (DnCNN layers — init)
  - segformer_b0_backbone_weights.pth     (noise backbone init)
  - segformer_b2_backbone_weights.pth     (image backbone init)
  - nfa_vit_brgen.pth                     (checkpoint treinado, chave 'model')
    ou checkpoint-XXX.pth do pacote BR-Gen
"""

from __future__ import annotations

import os
import shutil
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "models" / "imdlbenco" / "nfa_vit"
VENDOR = ROOT / "vendor" / "BR-Gen-main"

BAIDU_URL = "https://pan.baidu.com/s/1mqmMeoTzJf0TuIy17N6PFQ"
BAIDU_PASSWORD = "cclp"

INIT_FILES = {
    "noiseprint.pth": "DnCNN noiseprint (noise_extractor.layers)",
    "segformer_b0_backbone_weights.pth": "SegFormer-B0 backbone (noise branch)",
    "segformer_b2_backbone_weights.pth": "SegFormer-B2 backbone (image branch)",
}
CHECKPOINT_NAMES = ("nfa_vit_brgen.pth",)


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _ensure_vendor() -> bool:
    if VENDOR.is_dir():
        print(f"OK  vendor/{VENDOR.name}")
        return True
    zip_url = "https://github.com/clpbc/BR-Gen/archive/refs/heads/main.zip"
    print(f"Baixando BR-Gen de GitHub...")
    try:
        import zipfile

        archive = ROOT / "vendor" / "_BR-Gen.zip"
        urllib.request.urlretrieve(zip_url, archive)
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(ROOT / "vendor")
        extracted = ROOT / "vendor" / "BR-Gen-main"
        if not extracted.is_dir():
            for p in (ROOT / "vendor").glob("BR-Gen-*"):
                if p.is_dir():
                    p.rename(extracted)
                    break
        archive.unlink(missing_ok=True)
        print(f"OK  vendor/BR-Gen-main")
        return extracted.is_dir()
    except Exception as exc:
        print(f"FALHA  vendor BR-Gen: {exc}")
        print("  Clone manual: git clone https://github.com/clpbc/BR-Gen.git vendor/BR-Gen-main")
        return False


def _try_bubbliiiing_fallback(dest: Path, filename: str) -> bool:
    """Fallback parcial — formato incompativel com NFA-ViT; apenas aviso."""
    url = f"https://github.com/bubbliiiing/segformer-pytorch/releases/download/v1.0/{filename}"
    if dest.is_file() and dest.stat().st_size > 10_000:
        return True
    try:
        print(f"Tentando fallback {filename} (pode ser incompativel — prefira Baidu oficial)...")
        urllib.request.urlretrieve(url, dest)
        return dest.is_file() and dest.stat().st_size > 10_000
    except Exception:
        return False


def _validate_init(path: Path, name: str) -> bool:
    if not path.is_file() or path.stat().st_size < 10_000:
        return False
    try:
        import torch

        obj = torch.load(str(path), map_location="cpu", weights_only=False)
        if name == "noiseprint.pth":
            if isinstance(obj, dict) and "model" in obj and "module.conv1" in str(obj["model"].keys()):
                print(f"AVISO  {name} parece NPR ResNet (TruFor), nao DnCNN — use noiseprint.pth do pacote BR-Gen")
                return False
            keys = list(obj.keys()) if isinstance(obj, dict) else []
            if keys and keys[0].startswith("0."):
                print(f"OK  {name} (formato DnCNN Sequential)")
                return True
        if "segformer_b0" in name:
            if isinstance(obj, dict) and "patch_embed1.proj.weight" in obj:
                print(f"OK  {name} (patch_embed1 presente)")
                return True
            print(f"AVISO  {name} sem patch_embed1 — use pesos oficiais BR-Gen (Baidu)")
            return False
        if "segformer_b2" in name:
            if isinstance(obj, dict) and "patch_embed1.proj.weight" in obj:
                print(f"OK  {name}")
                return True
            print(f"AVISO  {name} sem patch_embed1 — use pesos oficiais BR-Gen (Baidu)")
            return False
    except Exception as exc:
        print(f"AVISO  nao foi possivel validar {name}: {exc}")
    return path.is_file() and path.stat().st_size > 10_000


def _validate_checkpoint(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size < 1_000_000:
        return False
    try:
        import torch

        obj = torch.load(str(path), map_location="cpu", weights_only=False)
        if isinstance(obj, dict) and "model" in obj:
            print(f"OK  {path.name} (checkpoint treinado BR-Gen)")
            return True
        print(f"AVISO  {path.name} sem chave 'model' — confira formato IMDLBenCo")
    except Exception as exc:
        print(f"FALHA  {path.name}: {exc}")
    return False


def main() -> int:
    base = Path(os.environ.get("IMDLBENCO_MODELS_DIR", ROOT / "models" / "imdlbenco")).resolve() / "nfa_vit"
    _ensure_dir(base)
    print(f"Destino: {base}\n")

    _ensure_vendor()

    print("--- Pesos de inicializacao (obrigatorios) ---")
    pending_init: list[str] = []
    for fname, desc in INIT_FILES.items():
        dest = base / fname
        if _validate_init(dest, fname):
            continue
        if "segformer" in fname:
            _try_bubbliiiing_fallback(dest, fname)
            if _validate_init(dest, fname):
                continue
        pending_init.append(fname)
        print(f"PENDENTE  {fname} — {desc}")
        print(f"          Copie para {dest}")

    print("\n--- Checkpoint treinado em BR-Gen (obrigatorio) ---")
    ckpt_ok = False
    for fname in CHECKPOINT_NAMES:
        dest = base / fname
        if _validate_checkpoint(dest):
            ckpt_ok = True
            break
    if not ckpt_ok:
        for p in sorted(base.glob("checkpoint-*.pth"), reverse=True):
            if _validate_checkpoint(p):
                ckpt_ok = True
                break
    if not ckpt_ok:
        print(f"PENDENTE  nfa_vit_brgen.pth ou checkpoint-*.pth")
        print(f"          Copie para {base}/")

    if pending_init or not ckpt_ok:
        print(f"\n=== Download manual (Baidu Netdisk) ===")
        print(f"URL:      {BAIDU_URL}")
        print(f"Senha:    {BAIDU_PASSWORD}")
        print("Conteudo: noiseprint.pth, segformer_b0/b2_backbone_weights.pth, checkpoint treinado")
        print("Referencia: https://github.com/clpbc/BR-Gen/tree/main/model_zoo/nfa_vit")
        return 1

    print("\nNFA-ViT: todos os pesos presentes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
