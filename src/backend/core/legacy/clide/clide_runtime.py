"""Runtime paths and availability for CLIDE synthetic image detection."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

WHITENING_GENERAL = "whitening_matrix_general.pt"
WHITENING_CARS = "whitening_matrix_cars.pt"
REP_GENERAL = "rep_matrix_general.pt"
REP_CARS = "rep_matrix_cars.pt"
CLIP_BACKBONE = "ViT-L/14"


def _workspace_root() -> Path:
    return Path(__file__).resolve().parents[5]


def _models_dir() -> Path:
    from app.config import get_settings

    return Path(get_settings().MODELS_DIR)


def clide_vendor_dir() -> Path:
    env = os.environ.get("CLIDE_VENDOR_DIR")
    if env:
        return Path(env).resolve()
    return _workspace_root() / "vendor" / "clide"


def clide_models_dir() -> Path:
    env = os.environ.get("CLIDE_MODELS_DIR")
    if env:
        return Path(env).resolve()
    return (_models_dir() / "clide").resolve()


def clide_clip_cache_dir() -> Path:
    env = os.environ.get("CLIDE_CLIP_CACHE")
    if env:
        return Path(env).resolve()
    return (clide_models_dir() / "clip").resolve()


def resolve_asset(filename: str) -> Path | None:
    for directory in (clide_models_dir(), clide_vendor_dir()):
        path = directory / filename
        if path.is_file() and path.stat().st_size > 1_000:
            return path.resolve()
    return None


def resolve_whitening_matrix(domain: str = "general") -> Path | None:
    filename = WHITENING_CARS if domain == "cars" else WHITENING_GENERAL
    return resolve_asset(filename)


def resolve_rep_matrix(domain: str = "general") -> Path | None:
    filename = REP_CARS if domain == "cars" else REP_GENERAL
    return resolve_asset(filename)


def clip_weights_cached() -> tuple[bool, str]:
    cache = clide_clip_cache_dir()
    if cache.is_dir() and any(p.is_file() and p.stat().st_size > 100_000_000 for p in cache.iterdir()):
        return True, ""
    return False, f"Peso OpenAI CLIP {CLIP_BACKBONE} ausente em {cache}"


def _package_ok() -> tuple[bool, str]:
    missing: list[str] = []
    for module in ("torch", "clip", "numpy", "scipy"):
        try:
            __import__(module)
        except ImportError:
            missing.append(module)
    if missing:
        return (
            False,
            "Dependencias CLIDE ausentes: "
            + ", ".join(missing)
            + ". Instale OpenAI CLIP e scipy no ambiente va-suite.",
        )
    if not clide_vendor_dir().is_dir():
        return False, f"Codigo CLIDE ausente em {clide_vendor_dir()}"
    if not (clide_vendor_dir() / "detection.py").is_file():
        return False, f"detection.py CLIDE ausente em {clide_vendor_dir()}"
    return True, ""


def clide_runtime_status() -> tuple[bool, str]:
    ok_pkg, reason = _package_ok()
    if not ok_pkg:
        return False, reason
    if resolve_rep_matrix("general") is None:
        return False, f"Representative matrix CLIDE ausente ({REP_GENERAL}). Execute: python scripts/download_clide_assets.py"
    clip_ok, clip_reason = clip_weights_cached()
    if not clip_ok:
        return False, clip_reason + ". Execute: python scripts/download_clide_assets.py"
    return True, ""


@lru_cache(maxsize=1)
def any_clide_ready() -> tuple[bool, str]:
    return clide_runtime_status()
