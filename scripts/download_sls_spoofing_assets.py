#!/usr/bin/env python3
"""Baixa pesos XLS-R e checkpoint SLS para deteccao de spoofing de audio."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS_DIR = ROOT / "models" / "sls_spoofing"
XLSR_URL = "https://dl.fbaipublicfiles.com/fairseq/wav2vec/xlsr2_300m.pt"
GDRIVE_FOLDER = "13vw_AX1jHdYndRu1edlgpdNJpCX8OnrH"


def _download_url(url: str, dest: Path) -> bool:
    if dest.is_file() and dest.stat().st_size > 1_000_000:
        print(f"OK  {dest.name} ({dest.stat().st_size} bytes)")
        return True
    print(f"Baixando {dest.name} …")
    tmp = dest.with_suffix(".part")
    import urllib.request

    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=3600) as resp:
        tmp.write_bytes(resp.read())
    shutil.move(str(tmp), dest)
    ok = dest.is_file() and dest.stat().st_size > 1_000_000
    print(f"{'OK' if ok else 'FALHA'}  {dest}")
    return ok


def _try_gdrive_weights(dest_dir: Path) -> bool:
    try:
        import gdown
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "gdown", "-q"])
        import gdown

    dest_dir.mkdir(parents=True, exist_ok=True)
    if any(dest_dir.rglob("MMpaper_model.pth")):
        print(f"OK  pesos SLS ja presentes em {dest_dir}")
        return True

    try:
        gdown.download_folder(
            f"https://drive.google.com/drive/folders/{GDRIVE_FOLDER}?usp=sharing",
            output=str(dest_dir),
            quiet=False,
            use_cookies=False,
        )
    except Exception as exc:
        print(f"Google Drive indisponivel ({exc})")
        return False

    candidates = list(dest_dir.rglob("MMpaper_model.pth"))
    if not candidates:
        return False
    target = dest_dir / "MMpaper_model.pth"
    if not target.is_file():
        shutil.copy2(max(candidates, key=lambda p: p.stat().st_size), target)
    print(f"OK  {target} ({target.stat().st_size} bytes)")
    return True


def main() -> None:
    models = Path(os.environ.get("SLS_SPOOFING_MODELS_DIR", MODELS_DIR)).resolve()
    models.mkdir(parents=True, exist_ok=True)

    xlsr = Path(os.environ.get("SLS_XLSR_WEIGHTS", models / "xlsr2_300m.pt")).resolve()
    if not _download_url(XLSR_URL, xlsr):
        raise SystemExit(1)

    weights_dir = models / "weights"
    if not _try_gdrive_weights(weights_dir):
        raise SystemExit("Falha ao baixar checkpoint SLS (MMpaper_model.pth)")

    vendor = ROOT / "Legados" / "audio" / "SLSforASVspoof-2021-DF"
    link = vendor / "xlsr2_300m.pt"
    if vendor.is_dir() and not link.exists():
        try:
            link.symlink_to(xlsr)
        except OSError:
            pass

    print("Assets SLS prontos.")


if __name__ == "__main__":
    main()
