#!/usr/bin/env python3
"""Baixa/prepara codigo e pesos oficiais B-Free (GRIP-UNINA).

Fonte: https://github.com/grip-unina/B-Free
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDOR_REPO = ROOT / "vendor" / "bfree"
VENDOR_CODE = VENDOR_REPO / "code"
TARGET = ROOT / "models" / "bfree" / "weights"
REPO = "https://github.com/grip-unina/B-Free"
MODEL_NAME = "BFREE_dino2reg4"


def main() -> None:
    _ensure_vendor()
    _copy_weights()


def _run(cmd: list[str], cwd: Path | None = None) -> None:
    subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=True)


def _ensure_vendor() -> None:
    if not VENDOR_REPO.is_dir():
        VENDOR_REPO.parent.mkdir(parents=True, exist_ok=True)
        _run(["git", "clone", REPO, str(VENDOR_REPO)])
    _run(["git", "lfs", "install"], cwd=VENDOR_REPO)
    _run(["git", "lfs", "pull"], cwd=VENDOR_REPO)
    _run(["git", "lfs", "checkout"], cwd=VENDOR_REPO)
    if not (VENDOR_CODE / "networks" / "__init__.py").is_file():
        raise SystemExit(f"Codigo B-Free invalido ou ausente em {VENDOR_CODE}")


def _copy_weights() -> None:
    src_dir = VENDOR_CODE / "weights" / MODEL_NAME
    dest_dir = TARGET / MODEL_NAME
    dest_dir.mkdir(parents=True, exist_ok=True)
    for name in ("config.yaml", "model_epoch_best.pth"):
        src = src_dir / name
        dest = dest_dir / name
        if not src.is_file() or (name.endswith(".pth") and src.stat().st_size < 1_000):
            raise SystemExit(f"Asset B-Free invalido ou ausente: {src}")
        shutil.copy2(src, dest)
        print(f"OK  {dest} ({dest.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
