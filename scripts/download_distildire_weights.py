#!/usr/bin/env python3
"""Baixa checkpoint DistilDIRE (HuggingFace) e modelo ADM 256x256."""

from __future__ import annotations

import os
import shutil
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "models" / "distildire" / "weights"

ADM_FILE = "256x256-adm.pt"
ADM_URL = (
    "https://openaipublic.blob.core.windows.net/diffusion/jul-2021/256x256_diffusion_uncond.pt"
)
CHECKPOINT_FILES = {
    "imagenet": "imagenet-distil-dire-11e.pth",
    "celebahq": "celebahq-distil-dire-34e.pth",
}
CHECKPOINT_URLS = {
    "imagenet": "https://huggingface.co/yevvonlim/distildire/resolve/main/imagenet-distil-dire-11e.pth",
    "celebahq": "https://huggingface.co/yevvonlim/distildire/resolve/main/celebahq-distil-dire-34e.pth",
}


def _download(url: str, dest: Path, *, min_bytes: int = 1_000_000) -> bool:
    if dest.is_file() and dest.stat().st_size >= min_bytes:
        print(f"OK  {dest.name} ({dest.stat().st_size} bytes)")
        return True
    print(f"Baixando {dest.name} …")
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=3600) as resp:
            with open(tmp, "wb") as fh:
                shutil.copyfileobj(resp, fh)
    except Exception as exc:
        print(f"FALHA {dest.name}: {exc}")
        if tmp.is_file():
            tmp.unlink(missing_ok=True)
        return False
    if tmp.stat().st_size < min_bytes:
        print(f"FALHA {dest.name}: arquivo muito pequeno ({tmp.stat().st_size} bytes)")
        tmp.unlink(missing_ok=True)
        return False
    shutil.move(str(tmp), dest)
    print(f"OK  {dest} ({dest.stat().st_size} bytes)")
    return True


def main() -> None:
    dest = Path(os.environ.get("DISTILDIRE_MODELS_DIR", TARGET.parent)).resolve() / "weights"
    dest.mkdir(parents=True, exist_ok=True)
    print(f"Destino: {dest}")

    ok = _download(ADM_URL, dest / ADM_FILE, min_bytes=50_000_000)
    for kind, fname in CHECKPOINT_FILES.items():
        ok = _download(CHECKPOINT_URLS[kind], dest / fname) and ok

    if not ok:
        raise SystemExit(1)
    print("Download DistilDIRE concluido.")


if __name__ == "__main__":
    main()
