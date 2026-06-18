"""Runtime paths and availability for Effort AIGI detection."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

EFFORT_VARIANTS = {
    "genimage": {
        "id": "genimage",
        "label": "GenImage (SD v1.4)",
        "filename": "effort_genimage_sdv14.pth",
        "drive_id": "1UXf1hC9FC1yV93uKwXSkdtepsgpIAU9d",
    },
    "chameleon": {
        "id": "chameleon",
        "label": "Chameleon (SD v1.4)",
        "filename": "effort_chameleon_sdv14.pth",
        "drive_id": "1GlJ1y4xmTdqV0FfIcyBwNNU6cQird9DR",
    },
}

CLIP_HF_ID = "openai/clip-vit-large-patch14"
CLIP_DRIVE_FOLDER = "1fm3Jd8lFMiSP1qgdmsxfqlJZGpr_bXsx"


def _workspace_root() -> Path:
    return Path(__file__).resolve().parents[5]


def effort_models_dir() -> Path:
    env = os.environ.get("EFFORT_MODELS_DIR")
    if env:
        return Path(env).resolve()
    from app.config import get_settings

    return (Path(get_settings().MODELS_DIR) / "effort").resolve()


def resolve_clip_path() -> Path | None:
    base = effort_models_dir()
    local = base / "clip-vit-large-patch14"
    if local.is_dir() and (local / "config.json").is_file():
        return local
    alt = base / "models--openai--clip-vit-large-patch14"
    if alt.is_dir():
        return alt
    return None


def resolve_checkpoint(variant: str = "genimage") -> Path | None:
    spec = EFFORT_VARIANTS.get(variant) or EFFORT_VARIANTS["genimage"]
    path = effort_models_dir() / spec["filename"]
    if path.is_file() and path.stat().st_size > 100_000:
        return path
    return None


def list_effort_variants() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for variant_id, spec in EFFORT_VARIANTS.items():
        path = effort_models_dir() / spec["filename"]
        ready = path.is_file() and path.stat().st_size > 100_000
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
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
        import yaml  # noqa: F401
    except ImportError as exc:
        return False, f"Dependencia Effort ausente: {exc}"
    return True, ""


def effort_runtime_status(*, variant: str = "genimage") -> tuple[bool, str]:
    ok_pkg, reason = _package_ok()
    if not ok_pkg:
        return False, reason

    if variant not in EFFORT_VARIANTS:
        return False, f"Variante Effort invalida: {variant}"

    ckpt = resolve_checkpoint(variant)
    if ckpt is None:
        fname = EFFORT_VARIANTS[variant]["filename"]
        return (
            False,
            f"Peso Effort ausente ({fname}). Execute: python scripts/download_effort_weights.py",
        )

    clip = resolve_clip_path()
    if clip is None:
        return (
            False,
            "CLIP ViT-L/14 ausente. Execute: python scripts/download_effort_weights.py "
            f"(ou defina cache HF para {CLIP_HF_ID})",
        )
    return True, ""


@lru_cache(maxsize=1)
def any_effort_ready() -> tuple[bool, str]:
    for variant_id in EFFORT_VARIANTS:
        ok, reason = effort_runtime_status(variant=variant_id)
        if ok:
            return True, ""
    return False, reason
