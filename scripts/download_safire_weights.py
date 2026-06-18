#!/usr/bin/env python3
"""Baixa pesos SAFIRE para models/safire/."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "models" / "safire"
SAM_URL = "https://dl.fbaipublicfiles.com/segment_anything/sam_vit_b_01ec64.pth"
SAFIRE_FILE_ID = "1SPd3D8_LTYRvDaE4iJgWr1F0xCMG5ds"
SAFIRE_BROWSER_URL = f"https://drive.google.com/file/d/{SAFIRE_FILE_ID}/view"


def _download_sam(dest: Path) -> None:
    import urllib.request

    out = dest / "sam_vit_b_01ec64.pth"
    if out.is_file() and out.stat().st_size > 10_000_000:
        print(f"OK  {out} ({out.stat().st_size // 1_000_000} MB)")
        return
    print(f"Baixando SAM ViT-B -> {out}")
    urllib.request.urlretrieve(SAM_URL, out)
    print(f"OK  {out} ({out.stat().st_size // 1_000_000} MB)")


def _try_gdown_safire(dest: Path) -> bool:
    try:
        import gdown
    except ImportError:
        return False

    out = dest / "safire.pth"
    try:
        gdown.download(id=SAFIRE_FILE_ID, output=str(out), quiet=False)
        return out.is_file() and out.stat().st_size > 1_000_000
    except Exception as exc:
        print(f"gdown falhou: {exc}")
        return False


def _try_requests_safire(dest: Path) -> bool:
    try:
        import requests
    except ImportError:
        return False

    out = dest / "safire.pth"
    session = requests.Session()
    url = "https://docs.google.com/uc?export=download"
    response = session.get(url, params={"id": SAFIRE_FILE_ID}, stream=True)
    for key, value in response.cookies.items():
        if key.startswith("download_warning"):
            response = session.get(url, params={"id": SAFIRE_FILE_ID, "confirm": value}, stream=True)
            break
    else:
        if "text/html" in response.headers.get("Content-Type", ""):
            token = re.search(r"confirm=([0-9A-Za-z_]+)", response.text)
            if token:
                response = session.get(
                    url, params={"id": SAFIRE_FILE_ID, "confirm": token.group(1)}, stream=True
                )

    ctype = response.headers.get("Content-Type", "")
    if response.status_code != 200 or "text/html" in ctype:
        return False

    with open(out, "wb") as f:
        for chunk in response.iter_content(1024 * 1024):
            if chunk:
                f.write(chunk)
    return out.is_file() and out.stat().st_size > 1_000_000


def _download_safire(dest: Path) -> None:
    out = dest / "safire.pth"
    if out.is_file() and out.stat().st_size > 1_000_000:
        print(f"OK  {out} ({out.stat().st_size // 1_000_000} MB)")
        return

    print("Tentando baixar safire.pth (Google Drive)...")
    if _try_gdown_safire(dest) or _try_requests_safire(dest):
        print(f"OK  {out} ({out.stat().st_size // 1_000_000} MB)")
        return

    print()
    print("NAO foi possivel baixar safire.pth automaticamente (permissao do Google Drive).")
    print("Baixe manualmente pelo navegador e copie para:")
    print(f"  {out}")
    print(f"Link: {SAFIRE_BROWSER_URL}")
    print()
    raise SystemExit(1)


def main() -> None:
    dest = Path(os.environ.get("SAFIRE_MODELS_DIR", TARGET)).resolve()
    dest.mkdir(parents=True, exist_ok=True)
    print(f"Destino: {dest}")
    _download_sam(dest)
    _download_safire(dest)
    print("Pesos SAFIRE prontos.")


if __name__ == "__main__":
    main()
