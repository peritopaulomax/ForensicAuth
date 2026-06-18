"""Runtime paths and availability for IAPL (CVPR 2026)."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

CLIP_FILENAME = "ViT-L-14.pt"
CLIP_URL = (
    "https://openaipublic.azureedge.net/clip/models/"
    "67061744bcf1c2805fdcbaeb8004775a0abeb6e8/ViT-L-14.pt"
)
MODELSCOPE_MODEL_ID = "yihengli/IAPL_pretrain"

IAPL_VARIANTS = {
    "genimage": {
        "id": "genimage",
        "label": "GenImage (SD v1.4)",
        "filename": "checkpoint_best_acc_sd14.pth",
        "dataset": "GenImage",
        "tta_steps": 2,
        "lr": 0.005,
    },
}


def _workspace_root() -> Path:
    return Path(__file__).resolve().parents[5]


def iapl_vendor_dir() -> Path:
    return _workspace_root() / "vendor" / "IAPL"


def iapl_models_dir() -> Path:
    env = os.environ.get("IAPL_MODELS_DIR")
    if env:
        return Path(env).resolve()
    from app.config import get_settings

    return (Path(get_settings().MODELS_DIR) / "iapl").resolve()


def resolve_clip_pt() -> Path | None:
    path = iapl_models_dir() / CLIP_FILENAME
    if path.is_file() and path.stat().st_size > 1_000_000:
        return path
    return None


def resolve_checkpoint(variant: str = "genimage") -> Path | None:
    spec = IAPL_VARIANTS.get(variant) or IAPL_VARIANTS["genimage"]
    path = iapl_models_dir() / spec["filename"]
    if path.is_file() and path.stat().st_size > 1_000_000:
        return path
    return None


def list_iapl_variants() -> list[dict]:
    out: list[dict] = []
    for variant_id, spec in IAPL_VARIANTS.items():
        path = iapl_models_dir() / spec["filename"]
        ready = path.is_file() and path.stat().st_size > 1_000_000
        out.append(
            {
                "id": variant_id,
                "label": spec["label"],
                "filename": spec["filename"],
                "ready": ready,
                "path": str(path) if ready else None,
            }
        )
    return out


def _package_ok() -> tuple[bool, str]:
    missing: list[str] = []
    for module in ("torch", "torchvision", "timm", "pytorch_wavelets"):
        try:
            __import__(module)
        except ImportError:
            missing.append(module)
    if missing:
        return (
            False,
            "Dependencias IAPL ausentes: "
            + ", ".join(missing)
            + ". Instale timm e pytorch_wavelets (requirements-gpu.txt).",
        )
    if not iapl_vendor_dir().is_dir():
        return False, f"Codigo IAPL ausente em {iapl_vendor_dir()}"
    return True, ""


def iapl_runtime_status(*, variant: str = "genimage") -> tuple[bool, str]:
    ok_pkg, reason = _package_ok()
    if not ok_pkg:
        return False, reason

    if variant not in IAPL_VARIANTS:
        return False, f"Variante IAPL invalida: {variant}"

    clip = resolve_clip_pt()
    if clip is None:
        return (
            False,
            f"CLIP ViT-L/14 ausente ({CLIP_FILENAME}). Execute: python scripts/download_iapl_weights.py",
        )

    ckpt = resolve_checkpoint(variant)
    if ckpt is None:
        fname = IAPL_VARIANTS[variant]["filename"]
        return (
            False,
            f"Peso IAPL ausente ({fname}). Execute: python scripts/download_iapl_weights.py",
        )
    return True, ""


@lru_cache(maxsize=1)
def any_iapl_ready() -> tuple[bool, str]:
    for variant_id in IAPL_VARIANTS:
        ok, reason = iapl_runtime_status(variant=variant_id)
        if ok:
            return True, ""
    return False, reason
