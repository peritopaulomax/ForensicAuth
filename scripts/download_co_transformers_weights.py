#!/usr/bin/env python3
"""Baixa codigo e pesos Co-Transformers (AAAI 2026).

Repositorio: https://github.com/ProgrameThinking/Co-Transformers
Pesos oficiais (Google Drive):
  https://drive.google.com/drive/folders/1aL9zagvJjhwAVdZXf73EeJaxS74iCnc-

Arquivos esperados:
  vendor/Co-Transformers-main/
  models/imdlbenco/co_transformers/mit_b3.pth          (ou reutiliza mesorch/)
  models/imdlbenco/co_transformers/noiseprint.pth        (ou reutiliza trufor/)
  models/imdlbenco/co_transformers/co_transformers.pth   (ou checkpoint-*.pth)
"""

from __future__ import annotations

import os
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "vendor" / "Co-Transformers-main"
TARGET = ROOT / "models" / "imdlbenco" / "co_transformers"
MESORCH_MIT_B3 = ROOT / "models" / "imdlbenco" / "mesorch" / "mit_b3.pth"
TRUFOR_NOISEPRINT = ROOT / "models" / "imdlbenco" / "trufor" / "noiseprint.pth"

GDRIVE_FOLDER_ID = "1aL9zagvJjhwAVdZXf73EeJaxS74iCnc-"
MIT_B3_URL = (
    "https://github.com/qubvel/segmentation_models.pytorch/releases/download/v0.0.2/mit_b3.pth"
)
MIN_CHECKPOINT_BYTES = 50_000_000


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _download_url(url: str, dest: Path, *, min_size: int = 0) -> bool:
    if dest.is_file() and dest.stat().st_size >= min_size:
        print(f"OK  {dest.name} ({dest.stat().st_size // 1_000_000} MB)")
        return True
    print(f"Baixando {dest.name}...")
    try:
        urllib.request.urlretrieve(url, dest)
    except Exception as exc:
        print(f"FALHA  {dest.name}: {exc}")
        return False
    ok = dest.is_file() and dest.stat().st_size >= min_size
    print("OK" if ok else "FALHA", dest)
    return ok


def _ensure_vendor() -> bool:
    if VENDOR.is_dir() and (VENDOR / "cotransformer.py").is_file():
        print(f"OK  vendor/{VENDOR.name}")
        return True
    archive = ROOT / "vendor" / "_Co-Transformers.zip"
    print("Baixando Co-Transformers de GitHub...")
    try:
        urllib.request.urlretrieve(
            "https://github.com/ProgrameThinking/Co-Transformers/archive/refs/heads/main.zip",
            archive,
        )
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(ROOT / "vendor")
        archive.unlink(missing_ok=True)
        if not VENDOR.is_dir():
            for p in (ROOT / "vendor").glob("Co-Transformers-*"):
                if p.is_dir():
                    p.rename(VENDOR)
                    break
        ok = VENDOR.is_dir()
        print("OK" if ok else "FALHA", VENDOR)
        return ok
    except Exception as exc:
        print(f"FALHA  vendor: {exc}")
        return False


def _validate_noiseprint(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size < 10_000:
        return False
    try:
        import torch

        obj = torch.load(str(path), map_location="cpu", weights_only=False)
        if isinstance(obj, dict) and "model" in obj:
            return False
        keys = list(obj.keys()) if isinstance(obj, dict) else []
        return bool(keys) and keys[0].startswith("0.")
    except Exception:
        return False


def _link_or_copy(src: Path, dest: Path) -> bool:
    if dest.is_file() and dest.stat().st_size > 1_000:
        print(f"OK  {dest.name}")
        return True
    if not src.is_file():
        return False
    _ensure_dir(dest.parent)
    try:
        dest.symlink_to(src.resolve())
    except OSError:
        shutil.copy2(src, dest)
    print(f"OK  {dest.name} <- {src}")
    return dest.is_file()


def _ensure_init_weights(base: Path) -> list[str]:
    pending: list[str] = []
    mit = base / "mit_b3.pth"
    if not _link_or_copy(MESORCH_MIT_B3, mit):
        if not _download_url(MIT_B3_URL, mit, min_size=1_000_000):
            pending.append("mit_b3.pth")

    np_dest = base / "noiseprint.pth"
    if _validate_noiseprint(np_dest):
        print(f"OK  {np_dest.name} (formato DnCNN)")
    else:
        np_dest.unlink(missing_ok=True)
        gdrive_np = base / "_gdrive" / "pretrained" / "noiseprint.pth"
        if _validate_noiseprint(gdrive_np):
            shutil.copy2(gdrive_np, np_dest)
            print(f"OK  {np_dest.name} (pacote Google Drive)")
        elif not _link_or_copy(TRUFOR_NOISEPRINT, np_dest) or not _validate_noiseprint(np_dest):
            np_dest.unlink(missing_ok=True)
            pending.append("noiseprint.pth (use o arquivo do Google Drive Co-Transformers, nao TruFor)")
    return pending


def _validate_checkpoint(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size < MIN_CHECKPOINT_BYTES:
        return False
    try:
        import torch

        obj = torch.load(str(path), map_location="cpu", weights_only=False)
        if isinstance(obj, dict) and "model" in obj:
            print(f"OK  {path.name} (checkpoint treinado, {path.stat().st_size // 1_000_000} MB)")
            return True
        print(f"AVISO  {path.name} sem chave 'model'")
    except Exception as exc:
        print(f"FALHA  {path.name}: {exc}")
    return False


def _publish_checkpoint(src: Path) -> None:
    canonical = TARGET / "co_transformers.pth"
    if canonical.resolve() == src.resolve():
        return
    if canonical.is_symlink() or canonical.is_file():
        canonical.unlink(missing_ok=True)
    try:
        canonical.symlink_to(src.relative_to(TARGET))
    except OSError:
        shutil.copy2(src, canonical)
    print(f"OK  {canonical} -> {src.name}")


def _try_gdown_checkpoint() -> Path | None:
    try:
        import gdown
    except ImportError:
        print("gdown ausente — pip install gdown")
        return None

    staging = TARGET / "_gdrive"
    _ensure_dir(staging)
    for p in list(staging.glob("checkpoint-*.pth")) + list(TARGET.glob("checkpoint-*.pth")):
        if _validate_checkpoint(p):
            return p

    print("Baixando checkpoint Co-Transformers (Google Drive)...")
    gdown.download_folder(
        id=GDRIVE_FOLDER_ID,
        output=str(staging),
        quiet=False,
        use_cookies=False,
    )
    candidates = sorted(
        list(staging.rglob("*.pth")),
        key=lambda p: p.stat().st_size,
        reverse=True,
    )
    for p in candidates:
        if _validate_checkpoint(p):
            return p
    return None


def main() -> int:
    base = Path(os.environ.get("IMDLBENCO_MODELS_DIR", ROOT / "models" / "imdlbenco")).resolve()
    target = base / "co_transformers"
    _ensure_dir(target)
    print(f"Destino: {target}\n")

    if not _ensure_vendor():
        return 1

    print("--- Pesos de inicializacao ---")
    pending_init = _ensure_init_weights(target)

    print("\n--- Checkpoint treinado ---")
    ckpt_ok = False
    canonical = target / "co_transformers.pth"
    if _validate_checkpoint(canonical):
        ckpt_ok = True
    if not ckpt_ok:
        for p in sorted(target.glob("checkpoint-*.pth"), reverse=True):
            if _validate_checkpoint(p):
                _publish_checkpoint(p)
                ckpt_ok = True
                break
    if not ckpt_ok:
        downloaded = _try_gdown_checkpoint()
        if downloaded is not None:
            dest = target / downloaded.name
            if downloaded.resolve() != dest.resolve():
                shutil.copy2(downloaded, dest)
            _publish_checkpoint(dest)
            ckpt_ok = True

    if pending_init or not ckpt_ok:
        print("\n=== Download manual (Google Drive) ===")
        print("URL: https://drive.google.com/drive/folders/1aL9zagvJjhwAVdZXf73EeJaxS74iCnc-")
        print(f"Salve checkpoint-*.pth em {target}/")
        if pending_init:
            print("Pendentes:", ", ".join(pending_init))
        return 1

    print("\nCo-Transformers: todos os pesos presentes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
