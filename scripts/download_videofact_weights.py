#!/usr/bin/env python3
"""Baixa pesos VideoFACT (Xfer + Deepfake) do Dropbox oficial."""

from __future__ import annotations

import os
import shutil
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "models" / "videofact" / "weights"

URLS = {
    "videofact_xfer.ckpt": (
        "https://www.dropbox.com/scl/fi/exkdmmp2krsbkc5fblld7/videofact_xfer.ckpt"
        "?rlkey=g52xhouc3h2yqrb5l2gfloiq7&dl=1"
    ),
    "videofact_df.ckpt": (
        "https://www.dropbox.com/scl/fi/euwth7njdi3nj3wi7o8zu/videofact_df.ckpt"
        "?rlkey=hwruc4bui47giukx5urlf1p5j&dl=1"
    ),
}


def _download(url: str, dest: Path) -> bool:
    if dest.is_file() and dest.stat().st_size > 1_000_000:
        print(f"OK  {dest.name} ({dest.stat().st_size} bytes)")
        return True
    print(f"Baixando {dest.name} …")
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=600) as resp:
        data = resp.read()
    tmp.write_bytes(data)
    shutil.move(str(tmp), dest)
    ok = dest.is_file() and dest.stat().st_size > 1_000_000
    print(f"{'OK' if ok else 'FALHA'}  {dest} ({dest.stat().st_size if dest.exists() else 0} bytes)")
    return ok


def main() -> None:
    dest_dir = Path(os.environ.get("VIDEOFACT_MODELS_DIR", TARGET.parent)).resolve() / "weights"
    dest_dir.mkdir(parents=True, exist_ok=True)
    print(f"Destino: {dest_dir}")

    ok_all = True
    for name, url in URLS.items():
        ok_all &= _download(url, dest_dir / name)

    vendor_cfg = ROOT / "vendor" / "videofact-wacv-2024" / "configs" / "default.yaml"
    if vendor_cfg.is_file():
        print(f"Config vendor: {vendor_cfg}")
    else:
        print("AVISO: vendor videofact-wacv-2024 ausente — clone/extraia o repositorio.")

    if ok_all:
        print("Download VideoFACT concluido.")
    else:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
