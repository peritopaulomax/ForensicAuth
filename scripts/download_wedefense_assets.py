#!/usr/bin/env python3
"""Baixa pesos WeDefense ASV2025 WavLM Base + MHFA para deteccao de spoofing."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS_DIR = ROOT / "models" / "wedefense_asv2025"
HF_REPO = "JYP2024/Wedefense_ASV2025_WavLM_Base_Pruning"

REQUIRED_FILES = (
    "config_pruned.yaml",
    "models/avg_model.pt",
    "pruned_model/pytorch_model.bin",
)


def _file_ok(path: Path, min_bytes: int) -> bool:
    return path.is_file() and path.stat().st_size >= min_bytes


def _download_hf(repo: str, dest: Path) -> None:
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        import subprocess

        subprocess.check_call([sys.executable, "-m", "pip", "install", "huggingface_hub", "-q"])
        from huggingface_hub import snapshot_download

    dest.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        repo_id=repo,
        local_dir=str(dest),
        local_dir_use_symlinks=False,
    )


def main() -> None:
    models = Path(os.environ.get("WEDEFENSE_MODELS_DIR", MODELS_DIR)).resolve()
    models.mkdir(parents=True, exist_ok=True)

    missing = [
        rel
        for rel in REQUIRED_FILES
        if not _file_ok(models / rel, 1_000 if rel.endswith(".yaml") else 1_000_000)
    ]
    if missing:
        print(f"Baixando {HF_REPO} …")
        _download_hf(HF_REPO, models)
        missing = [
            rel
            for rel in REQUIRED_FILES
            if not _file_ok(models / rel, 1_000 if rel.endswith(".yaml") else 1_000_000)
        ]

    if missing:
        raise SystemExit(f"Arquivos ausentes apos download: {', '.join(missing)}")

    final_model = models / "models" / "final_model.pt"
    if final_model.is_file() and final_model.stat().st_size < 1000:
        print(f"AVISO: {final_model} e ponteiro HF — usar models/avg_model.pt")

    print("Assets WeDefense prontos.")


if __name__ == "__main__":
    main()
