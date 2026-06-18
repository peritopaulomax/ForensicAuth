#!/usr/bin/env python3
"""Baixa pesos baseline do projeto lukasHoel/fake-video-detection."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "models" / "lowres_fake_video" / "weights" / "baseline_xception.pt"
GDRIVE_FOLDER = "1m_XR1HWRMkXv-pS2bUxo3hEHsMeJ3fxN"

# Fallback publico: Xception treinado em FF++ (DeepfakeBench) — frame-a-frame compativel.
FALLBACK_URL = (
    "https://github.com/SCLBD/DeepfakeBench/releases/download/v1.0.1/xception_best.pth"
)


def _download_url(url: str, dest: Path) -> bool:
    if dest.is_file() and dest.stat().st_size > 10_000:
        print(f"OK  {dest.name} ({dest.stat().st_size} bytes)")
        return True
    print(f"Baixando {dest.name} …")
    tmp = dest.with_suffix(".part")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=600) as resp:
        tmp.write_bytes(resp.read())
    shutil.move(str(tmp), dest)
    ok = dest.is_file() and dest.stat().st_size > 10_000
    print(f"{'OK' if ok else 'FALHA'}  {dest}")
    return ok


def _try_gdrive(dest: Path) -> bool:
    try:
        import gdown
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "gdown", "-q"])
        import gdown

    tmp_dir = dest.parent / "_gdrive_tmp"
    if tmp_dir.is_dir():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    try:
        gdown.download_folder(
            id=GDRIVE_FOLDER,
            output=str(tmp_dir),
            quiet=False,
            use_cookies=False,
        )
    except Exception as exc:
        print(f"Google Drive indisponivel ({exc})")
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return False

    candidates = sorted(tmp_dir.rglob("baseline*.pt"))
    if not candidates:
        candidates = sorted(tmp_dir.rglob("*.pt"))
    if not candidates:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return False
    src = max(candidates, key=lambda p: p.stat().st_size)
    shutil.copy2(src, dest)
    shutil.rmtree(tmp_dir, ignore_errors=True)
    print(f"OK  {dest} via Google Drive ({dest.stat().st_size} bytes)")
    return True


def main() -> None:
    dest = Path(os.environ.get("LFV_WEIGHTS_PATH", TARGET)).resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and dest.stat().st_size > 10_000:
        print(f"OK  {dest}")
        return

    print("Tentando Google Drive oficial do projeto TUM…")
    if _try_gdrive(dest):
        return

    print(
        "\nAVISO: pasta Google Drive do repositorio retornou 404/permissao.\n"
        "Usando fallback DeepfakeBench xception_best.pth (detector FF++, frame-a-frame).\n"
        "Para o checkpoint original TUM, baixe manualmente de:\n"
        f"  https://drive.google.com/drive/folders/{GDRIVE_FOLDER}\n"
        f"e copie para {dest}\n"
    )
    if not _download_url(FALLBACK_URL, dest):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
