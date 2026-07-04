"""Runtime paths and bootstrap for WeDefense ASV2025 WavLM + MHFA spoofing."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional, Tuple

AVG_CHECKPOINT_NAME = "avg_model.pt"
PRUNED_UPSTREAM_NAME = "pytorch_model.bin"
LOCAL_CONFIG_NAME = "config_pruned_local.yaml"
SOURCE_CONFIG_NAME = "config_pruned.yaml"

_WEDEFENSE_BOOTSTRAPPED = False


def _workspace_root() -> Path:
    return Path(__file__).resolve().parents[5]


def _vendor_root() -> Path:
    return _workspace_root() / "Legados" / "audio" / "WeDefense"


def _models_dir() -> Path:
    from app.config import get_settings

    return (Path(get_settings().MODELS_DIR) / "wedefense_asv2025").resolve()


def _fallback_models_dir() -> Path:
    return (_workspace_root() / "models" / "wedefense_asv2025").resolve()


def _candidate_model_dirs() -> list[Path]:
    env = os.environ.get("WEDEFENSE_MODELS_DIR", "").strip()
    candidates: list[Path] = []
    if env:
        candidates.append(Path(env).resolve())
    primary = _models_dir()
    candidates.append(primary)
    fallback = _fallback_models_dir()
    if fallback != primary:
        candidates.append(fallback)
    return candidates


def resolve_model_dir() -> Optional[Path]:
    for directory in _candidate_model_dirs():
        if (directory / "models" / AVG_CHECKPOINT_NAME).is_file():
            return directory.resolve()
    return None


def resolve_avg_checkpoint_path() -> Optional[Path]:
    env = os.environ.get("WEDEFENSE_CHECKPOINT", "").strip()
    if env and Path(env).is_file():
        return Path(env).resolve()
    model_dir = resolve_model_dir()
    if model_dir is None:
        return None
    path = model_dir / "models" / AVG_CHECKPOINT_NAME
    return path.resolve() if path.is_file() else None


def resolve_pruned_upstream_path() -> Optional[Path]:
    env = os.environ.get("WEDEFENSE_PRUNED_UPSTREAM", "").strip()
    if env and Path(env).is_file():
        return Path(env).resolve()
    model_dir = resolve_model_dir()
    if model_dir is None:
        return None
    path = model_dir / "pruned_model" / PRUNED_UPSTREAM_NAME
    return path.resolve() if path.is_file() else None


def resolve_local_config_path() -> Optional[Path]:
    model_dir = resolve_model_dir()
    if model_dir is None:
        return None
    return (model_dir / LOCAL_CONFIG_NAME).resolve()


def ensure_local_config() -> Path:
    """Write config_pruned_local.yaml with absolute upstream path."""
    import yaml

    model_dir = resolve_model_dir()
    if model_dir is None:
        raise RuntimeError("Diretorio de modelos WeDefense nao encontrado")
    upstream = resolve_pruned_upstream_path()
    if upstream is None:
        raise RuntimeError("Upstream pruned (pytorch_model.bin) ausente")

    source = model_dir / SOURCE_CONFIG_NAME
    if not source.is_file():
        raise RuntimeError(f"Config base ausente: {source}")

    with open(source, encoding="utf-8") as fin:
        cfg = yaml.safe_load(fin)

    hf_args = cfg["dataset_args"]["huggingface_args"]["upstream_args"]
    hf_args["path_or_url"] = str(upstream)

    dest = model_dir / LOCAL_CONFIG_NAME
    with open(dest, "w", encoding="utf-8") as fout:
        yaml.dump(cfg, fout, default_flow_style=False, allow_unicode=True)
    return dest.resolve()


def bootstrap_wedefense() -> None:
    """Insert vendored WeDefense on sys.path."""
    global _WEDEFENSE_BOOTSTRAPPED
    if _WEDEFENSE_BOOTSTRAPPED:
        return

    vendor_root = _vendor_root()
    if not vendor_root.is_dir():
        raise RuntimeError(f"Vendor WeDefense ausente em {vendor_root}")

    vendor_str = str(vendor_root)
    if vendor_str not in sys.path:
        sys.path.insert(0, vendor_str)

    ensure_local_config()
    _WEDEFENSE_BOOTSTRAPPED = True


def runtime_status() -> Tuple[bool, str]:
    if not _vendor_root().is_dir():
        return False, "Vendor WeDefense ausente (Legados/audio/WeDefense)"
    if resolve_avg_checkpoint_path() is None:
        return False, "Checkpoint WeDefense ausente (models/wedefense_asv2025/models/avg_model.pt)"
    if resolve_pruned_upstream_path() is None:
        return False, "Upstream pruned ausente (models/wedefense_asv2025/pruned_model/pytorch_model.bin)"
    try:
        bootstrap_wedefense()
        import wedefense  # noqa: F401
    except Exception as exc:
        return False, f"WeDefense bootstrap falhou: {exc}"
    return True, ""
