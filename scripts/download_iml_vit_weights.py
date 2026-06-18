#!/usr/bin/env python3
"""Baixa pesos IML-ViT para models/iml_vit/."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "models" / "iml_vit"
CHECKPOINT = "iml-vit_checkpoint.pth"
FILE_ID = "1xXJGJPW1i5j9Pc1JKd7fJmIAQkvt9jY7"
BROWSER_URL = f"https://drive.google.com/file/d/{FILE_ID}/view"


def _try_gdown(dest: Path) -> bool:
    try:
        import gdown
    except ImportError:
        return False

    out = dest / CHECKPOINT
    try:
        gdown.download(id=FILE_ID, output=str(out), quiet=False)
        return out.is_file() and out.stat().st_size > 1_000_000
    except Exception as exc:
        print(f"gdown falhou: {exc}")
        return False


def _try_requests(dest: Path) -> bool:
    try:
        import requests
    except ImportError:
        return False

    out = dest / CHECKPOINT
    session = requests.Session()
    url = "https://docs.google.com/uc?export=download"
    response = session.get(url, params={"id": FILE_ID}, stream=True)
    for key, value in response.cookies.items():
        if key.startswith("download_warning"):
            response = session.get(url, params={"id": FILE_ID, "confirm": value}, stream=True)
            break
    else:
        if "text/html" in response.headers.get("Content-Type", ""):
            token = re.search(r"confirm=([0-9A-Za-z_]+)", response.text)
            if token:
                response = session.get(
                    url, params={"id": FILE_ID, "confirm": token.group(1)}, stream=True
                )

    ctype = response.headers.get("Content-Type", "")
    if response.status_code != 200 or "text/html" in ctype:
        return False

    with open(out, "wb") as f:
        for chunk in response.iter_content(1024 * 1024):
            if chunk:
                f.write(chunk)
    return out.is_file() and out.stat().st_size > 1_000_000


def main() -> None:
    dest = Path(os.environ.get("IML_VIT_MODELS_DIR", TARGET)).resolve()
    dest.mkdir(parents=True, exist_ok=True)
    out = dest / CHECKPOINT

    if out.is_file() and out.stat().st_size > 1_000_000:
        print(f"OK  {out} ({out.stat().st_size // 1_000_000} MB)")
        return

    print(f"Destino: {dest}")
    print("Tentando baixar iml-vit_checkpoint.pth (Google Drive)...")
    if _try_gdown(dest) or _try_requests(dest):
        print(f"OK  {out} ({out.stat().st_size // 1_000_000} MB)")
        return

    print()
    print("NAO foi possivel baixar o checkpoint automaticamente.")
    print("Baixe manualmente e copie para:")
    print(f"  {out}")
    print(f"Link: {BROWSER_URL}")
    print()
    raise SystemExit(1)


if __name__ == "__main__":
    main()
