#!/usr/bin/env python3
"""Baixa pesos CAMO (BitMind bm-ucf) e predictor dlib para deteccao sintetica."""

from __future__ import annotations

import os
import shutil
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "models" / "camo"
HF_REPO = "bitmind/bm-ucf"
WEIGHT_FILES = (
    "bm-general-v1.pth",
    "bm-faces-v1.pth",
    "xception-best.pth",
)
CONFIG_FILES = (
    "bm-general-config-v1.yaml",
    "bm-faces-config-v1.yaml",
)
DLIB_PREDICTOR = "shape_predictor_81_face_landmarks.dat"
DLIB_URL = (
    "https://huggingface.co/spaces/liangtian/birthdayCrown/resolve/"
    "e96083d163606933a2cc74be372895f3cc5d1b96/shape_predictor_81_face_landmarks.dat"
)


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _download_hf(repo: str, filename: str, dest_dir: Path) -> bool:
    dest = dest_dir / filename
    if dest.is_file() and dest.stat().st_size > 1000:
        print(f"OK  {filename} ({dest.stat().st_size} bytes)")
        return True
    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        print("FALHA  huggingface_hub ausente. pip install huggingface_hub")
        return False
    print(f"Baixando {repo}/{filename} …")
    path = hf_hub_download(repo, filename, local_dir=str(dest_dir))
    ok = Path(path).is_file()
    print(f"{'OK' if ok else 'FALHA'}  {dest}")
    return ok


def _download_dlib(dest: Path) -> bool:
    if dest.is_file() and dest.stat().st_size > 1_000_000:
        print(f"OK  {dest.name} ({dest.stat().st_size} bytes)")
        return True
    print(f"Baixando {DLIB_PREDICTOR} …")
    tmp = dest.with_suffix(".dat.part")
    urllib.request.urlretrieve(DLIB_URL, tmp)
    shutil.move(str(tmp), dest)
    ok = dest.is_file() and dest.stat().st_size > 1_000_000
    print(f"{'OK' if ok else 'FALHA'}  {dest}")
    return ok


def main() -> None:
    base = _ensure_dir(Path(os.environ.get("CAMO_MODELS_DIR", TARGET)).resolve())
    weights = _ensure_dir(base / "weights")
    configs = _ensure_dir(base / "configs")
    print(f"Destino: {base}")

    ok_all = True
    for name in WEIGHT_FILES:
        ok_all &= _download_hf(HF_REPO, name, weights)
    for name in CONFIG_FILES:
        ok_all &= _download_hf(HF_REPO, name, configs)
    ok_all &= _download_dlib(base / DLIB_PREDICTOR)

    if ok_all:
        print("Download CAMO concluido.")
    else:
        print("Download CAMO incompleto — verifique rede e dependencias.")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
