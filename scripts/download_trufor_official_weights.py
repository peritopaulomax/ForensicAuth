#!/usr/bin/env python3
"""Baixa pesos oficiais TruFor (GRIP-UNINA test_docker)."""

from __future__ import annotations

import hashlib
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "models" / "imdlbenco" / "trufor"
URL = "https://www.grip.unina.it/download/prog/TruFor/TruFor_weights.zip"
EXPECTED_MD5 = "7bee48f3476c75616c3c5721ab256ff8"
CKPT_NAME = "trufor.pth.tar"


def main() -> int:
    TARGET.mkdir(parents=True, exist_ok=True)
    zip_path = TARGET / "TruFor_weights.zip"
    ckpt_path = TARGET / CKPT_NAME

    if ckpt_path.is_file() and ckpt_path.stat().st_size > 1_000_000:
        print(f"OK  {ckpt_path}")
        return 0

    print(f"Baixando {URL} ...")
    urllib.request.urlretrieve(URL, zip_path)
    md5 = hashlib.md5(zip_path.read_bytes()).hexdigest()
    if md5 != EXPECTED_MD5:
        print(f"AVISO  MD5 inesperado: {md5} (esperado {EXPECTED_MD5})")

    with zipfile.ZipFile(zip_path) as zf:
        for name in zf.namelist():
            if name.endswith(CKPT_NAME):
                ckpt_path.write_bytes(zf.read(name))
                print(f"OK  {ckpt_path}")
                return 0
        # flat zip
        for name in zf.namelist():
            if name.endswith("/"):
                continue
            out = TARGET / Path(name).name
            if out.suffix in {".tar", ".pth", ".pth.tar"}:
                out.write_bytes(zf.read(name))
                print(f"OK  {out}")
                return 0

    print("FALHA  checkpoint nao encontrado no zip")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
