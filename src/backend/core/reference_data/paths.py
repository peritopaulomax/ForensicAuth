"""Canonical paths for LR / typicality reference data.

Runtime (product) uses **only** ``REFERENCE_DATA_DIR`` (publish)::

    $REFERENCE_DATA_DIR/
      cache/
      audio_spoofing/{catalog,populations,features}/
      synthetic_image/{catalog,populations,features}/

Staging for calibration (ops / offline) — not part of the runtime happy path::

    $REFERENCE_BUILD_DIR/   heavy samples + augmented (outside git)
    $BASES_ROOT/            immutable corpora (e.g. /mnt/bases)
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path


def project_root() -> Path:
    """Repository root (``VA Suite`` / ForensicAuth).

    Em producao usa FORENSICAUTH_WORKSPACE_ROOT (ex.: /opt/forensicauth).
    Em dev, sobe ate a raiz do repo a partir do arquivo atual.
    """
    env = os.environ.get("FORENSICAUTH_WORKSPACE_ROOT")
    if env:
        return Path(env).resolve()
    return Path(__file__).resolve().parents[4]


def _resolve_under_project(raw: str) -> Path:
    """Resolve a path; relative values are always against the repo root (not CWD)."""
    p = Path(raw).expanduser()
    if not p.is_absolute():
        return (project_root() / p).resolve()
    return p.resolve()


def _looks_like_publish_root(path: Path) -> bool:
    """Heuristic: published tree has audio and/or synthetic feature scores."""
    scores = path / "audio_spoofing" / "features" / "scores"
    syn = path / "synthetic_image" / "features" / "scores"
    try:
        return scores.is_dir() or syn.is_dir()
    except OSError:
        return False


@lru_cache(maxsize=1)
def get_reference_data_root() -> Path:
    """Published reference assets (env override or ``<repo>/reference_data``).

    Relative env values are resolved from the **repository root**, not process CWD
    (uvicorn often runs with cwd=``src/backend``, which used to create a wrong
    ``src/backend/reference_data``).
    """
    env = (
        (os.environ.get("FORENSICAUTH_REFERENCE_DATA_DIR") or "").strip()
        or (os.environ.get("REFERENCE_DATA_DIR") or "").strip()
    )
    canonical = (project_root() / "reference_data").resolve()
    if not env:
        return canonical

    resolved = _resolve_under_project(env)
    # Heal the classic misconfig: Settings resolved ``./reference_data`` while cwd
    # was ``src/backend``, producing an empty tree under the backend package.
    backend_accident = (project_root() / "src" / "backend" / "reference_data").resolve()
    if resolved == backend_accident and _looks_like_publish_root(canonical):
        return canonical
    return resolved


@lru_cache(maxsize=1)
def get_reference_build_root() -> Path:
    """Heavy build/staging root (samples + augmented) — outside the git tree by default."""
    env = (
        (os.environ.get("FORENSICAUTH_REFERENCE_BUILD_DIR") or "").strip()
        or (os.environ.get("REFERENCE_BUILD_DIR") or "").strip()
    )
    if env:
        return _resolve_under_project(env)
    return (project_root().parent / "va-reference_build").resolve()


@lru_cache(maxsize=1)
def get_bases_root() -> Path:
    """Immutable corpora mount (ASVspoof, GenImage, …)."""
    env = (
        (os.environ.get("FORENSICAUTH_BASES_ROOT") or "").strip()
        or (os.environ.get("BASES_ROOT") or "").strip()
    )
    if env:
        return _resolve_under_project(env)
    return Path("/mnt/bases").expanduser().resolve()


def ensure_reference_layout(root: Path | None = None) -> Path:
    """Create the published directory tree; return the root used."""
    base = root or get_reference_data_root()
    for rel in (
        "cache",
        "audio_spoofing/catalog",
        "audio_spoofing/populations",
        "audio_spoofing/features/scores",
        "audio_spoofing/features/representations",
        "synthetic_image/catalog",
        "synthetic_image/populations",
        "synthetic_image/features/scores",
        "synthetic_image/features/representations",
    ):
        (base / rel).mkdir(parents=True, exist_ok=True)
    return base


def ensure_build_layout(root: Path | None = None) -> Path:
    """Create the offline build/staging tree; return the root used."""
    base = root or get_reference_build_root()
    for rel in (
        "audio_spoofing/samples/full",
        "audio_spoofing/samples/augmented",
        "audio_spoofing/inventory",
        "synthetic_image/samples",
    ):
        (base / rel).mkdir(parents=True, exist_ok=True)
    return base


def lr_cache_dir() -> Path:
    """Shared joblib cache for calibrated LR models / typicality refs.

    reference_data/ pode ser read-only NFS. Se falhar, usa data/cache/.
    """
    path = get_reference_data_root() / "cache"
    try:
        path.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        path = get_reference_data_root().parent / "data" / "cache" / "reference_data"
        path.mkdir(parents=True, exist_ok=True)
    return path


def audio_domain_root() -> Path:
    return get_reference_data_root() / "audio_spoofing"


def synthetic_domain_root() -> Path:
    return get_reference_data_root() / "synthetic_image"


def audio_score_matrix() -> Path:
    return (
        get_reference_data_root()
        / "audio_spoofing"
        / "features"
        / "scores"
        / "lr_scores_balanced_full.csv"
    )


def audio_augmented_score_matrix() -> Path:
    return (
        get_reference_data_root()
        / "audio_spoofing"
        / "features"
        / "scores"
        / "lr_scores_balanced_full_augmented.csv"
    )


def audio_representations_matrix() -> Path:
    return (
        get_reference_data_root()
        / "audio_spoofing"
        / "features"
        / "representations"
        / "representations.csv"
    )


def audio_features_scores_dir() -> Path:
    return get_reference_data_root() / "audio_spoofing" / "features" / "scores"


def audio_representations_root() -> Path:
    return get_reference_data_root() / "audio_spoofing" / "features" / "representations"


def _dir_has_payload(path: Path) -> bool:
    """True if directory tree contains at least one regular file."""
    if not path.is_dir():
        return False
    try:
        return any(p.is_file() for p in path.rglob("*"))
    except OSError:
        return False


def _legacy_audio_samples() -> Path:
    return get_reference_data_root() / "audio_spoofing" / "working" / "samples"


def audio_samples_root() -> Path:
    """Calibration samples under BUILD (ops). Not used by publish/runtime LR."""
    build = get_reference_build_root() / "audio_spoofing" / "samples"
    legacy = _legacy_audio_samples()
    if _dir_has_payload(build):
        return build
    if _dir_has_payload(legacy):
        return legacy
    return build


def audio_working_samples_root() -> Path:
    """Deprecated alias for :func:`audio_samples_root` (ops/calibration)."""
    return audio_samples_root()


def audio_inventory_dir() -> Path:
    build = get_reference_build_root() / "audio_spoofing" / "inventory"
    legacy = get_reference_data_root() / "audio_spoofing" / "working" / "inventory"
    if _dir_has_payload(build):
        return build
    if _dir_has_payload(legacy):
        return legacy
    return build


def synthetic_samples_root() -> Path:
    build = get_reference_build_root() / "synthetic_image" / "samples"
    legacy = get_reference_data_root() / "synthetic_image" / "working"
    if _dir_has_payload(build):
        return build
    if _dir_has_payload(legacy):
        return legacy
    return build


def synthetic_score_matrix() -> Path:
    return (
        get_reference_data_root()
        / "synthetic_image"
        / "features"
        / "scores"
        / "lr_scores_balanced_full.csv"
    )


def synthetic_augmented_score_matrix() -> Path:
    return (
        get_reference_data_root()
        / "synthetic_image"
        / "features"
        / "scores"
        / "lr_scores_balanced_full_augmented.csv"
    )


def synthetic_representations_matrix() -> Path:
    return (
        get_reference_data_root()
        / "synthetic_image"
        / "features"
        / "representations"
        / "representations.csv"
    )


def synthetic_features_scores_dir() -> Path:
    return get_reference_data_root() / "synthetic_image" / "features" / "scores"


def synthetic_representations_root() -> Path:
    return get_reference_data_root() / "synthetic_image" / "features" / "representations"


def clear_path_cache() -> None:
    """Clear cached root resolution (tests / after env change)."""
    get_reference_data_root.cache_clear()
    get_reference_build_root.cache_clear()
    get_bases_root.cache_clear()
