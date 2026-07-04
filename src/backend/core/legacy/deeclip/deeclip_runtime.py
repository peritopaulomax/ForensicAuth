"""Runtime paths and availability for DeeCLIP synthetic image detection."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

CHECKPOINT_FILENAME = "deeclip_weight_complete_with_lora_5.pth"
DEECLIP_REPO = "mamadou-keita/deeclip"
DEECLIP_WEIGHTS_URL = (
    "https://www.dropbox.com/scl/fi/ttiqnbxu8atz4on5gqvgd/"
    "deeclip_weight_complete_with_lora_5.pth?rlkey=6xznuvriabkqfdcofhi1pbihu&st=fk02k7hf&dl=1"
)
CLIP_MODEL_ID = "openai/clip-vit-large-patch14"


def _workspace_root() -> Path:
    return Path(__file__).resolve().parents[5]


def _models_dir() -> Path:
    from app.config import get_settings

    return Path(get_settings().MODELS_DIR)


def deeclip_vendor_dir() -> Path:
    env = os.environ.get("DEECLIP_VENDOR_DIR")
    if env:
        return Path(env).resolve()
    return _workspace_root() / "vendor" / "deeclip"


def deeclip_models_dir() -> Path:
    env = os.environ.get("DEECLIP_MODELS_DIR")
    if env:
        return Path(env).resolve()
    return (_models_dir() / "deeclip").resolve()


def deeclip_hf_cache_dir() -> Path:
    env = os.environ.get("DEECLIP_HF_CACHE")
    if env:
        return Path(env).resolve()
    return (deeclip_models_dir() / "huggingface").resolve()


def resolve_checkpoint() -> Path | None:
    path = deeclip_models_dir() / "weights" / CHECKPOINT_FILENAME
    if path.is_file() and path.stat().st_size > 100_000_000:
        return path
    vendor_path = deeclip_vendor_dir() / "weights" / CHECKPOINT_FILENAME
    if vendor_path.is_file() and vendor_path.stat().st_size > 100_000_000:
        return vendor_path
    return None


def _hf_cache_folder(model_id: str) -> str:
    return "models--" + model_id.replace("/", "--")


def resolve_clip_snapshot_path() -> Path | None:
    folder = deeclip_hf_cache_dir() / _hf_cache_folder(CLIP_MODEL_ID)
    if not folder.is_dir():
        return None

    refs_main = folder / "refs" / "main"
    if refs_main.is_file():
        revision = refs_main.read_text(encoding="utf-8").strip()
        snapshot = folder / "snapshots" / revision
        if snapshot.is_dir():
            return snapshot.resolve()

    snapshots_dir = folder / "snapshots"
    if snapshots_dir.is_dir():
        candidates = sorted(
            (p for p in snapshots_dir.iterdir() if p.is_dir()),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if candidates:
            return candidates[0].resolve()
    return None


def _package_ok() -> tuple[bool, str]:
    missing: list[str] = []
    for module in ("torch", "torchvision", "transformers", "peft"):
        try:
            __import__(module)
        except ImportError:
            missing.append(module)
    if missing:
        return (
            False,
            "Dependencias DeeCLIP ausentes: "
            + ", ".join(missing)
            + ". Instale: pip install -r requirements-gpu.txt",
        )
    if not deeclip_vendor_dir().is_dir():
        return False, f"Codigo DeeCLIP ausente em {deeclip_vendor_dir()}"
    if not (deeclip_vendor_dir() / "model.py").is_file():
        return False, f"model.py DeeCLIP ausente em {deeclip_vendor_dir()}"
    return True, ""


def deeclip_runtime_status() -> tuple[bool, str]:
    ok_pkg, reason = _package_ok()
    if not ok_pkg:
        return False, reason
    if resolve_checkpoint() is None:
        return (
            False,
            f"Peso DeeCLIP ausente ({CHECKPOINT_FILENAME}). "
            "Execute: python scripts/download_deeclip_assets.py",
        )
    if resolve_clip_snapshot_path() is None:
        return (
            False,
            f"Cache HuggingFace ausente para {CLIP_MODEL_ID}. "
            "Execute: python scripts/download_deeclip_assets.py",
        )
    return True, ""


@lru_cache(maxsize=1)
def any_deeclip_ready() -> tuple[bool, str]:
    return deeclip_runtime_status()
