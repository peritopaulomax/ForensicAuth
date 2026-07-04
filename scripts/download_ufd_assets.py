#!/usr/bin/env python3
"""Baixa pesos do UniversalFakeDetect e cache OpenAI CLIP ViT-L/14."""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "models" / "universal_fake_detect"


def main() -> None:
    TARGET.mkdir(parents=True, exist_ok=True)

    try:
        from huggingface_hub import hf_hub_download
    except ImportError as exc:
        raise SystemExit("Instale huggingface_hub para baixar fc_weights.pth do UniversalFakeDetect.") from exc

    src = Path(
        hf_hub_download(
            repo_id="siddharthksah/deepsafe-weights",
            filename="universalfakedetect/fc_weights.pth",
        )
    )
    dest = TARGET / "fc_weights.pth"
    shutil.copy2(src, dest)
    print(f"OK  UniversalFakeDetect FC: {dest} ({dest.stat().st_size} bytes)")

    try:
        from clip.clip import _MODELS, _download
    except ImportError as exc:
        raise SystemExit("Instale OpenAI CLIP antes de baixar o peso ViT-L/14.") from exc

    clip_cache = TARGET / "clip"
    clip_cache.mkdir(parents=True, exist_ok=True)
    path = _download(_MODELS["ViT-L/14"], str(clip_cache))
    print(f"OK  CLIP ViT-L/14: {path}")


if __name__ == "__main__":
    main()

