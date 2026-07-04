"""Runtime paths and fairseq bootstrap for SLS audio spoofing detection."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional, Tuple

XLSR_WEIGHTS_NAME = "xlsr2_300m.pt"
SLS_CHECKPOINT_NAME = "MMpaper_model.pth"

_FAIRSEQ_BOOTSTRAPPED = False


def _workspace_root() -> Path:
    return Path(__file__).resolve().parents[5]


def _vendor_root() -> Path:
    return _workspace_root() / "Legados" / "audio" / "SLSforASVspoof-2021-DF"


def _fairseq_root() -> Path:
    return _vendor_root() / "fairseq-a54021305d6b3c4c5959ac9395135f63202db8f1"


def _models_dir() -> Path:
    from app.config import get_settings

    return (Path(get_settings().MODELS_DIR) / "sls_spoofing").resolve()


def _fallback_models_dir() -> Path:
    """Fallback when MODELS_DIR relativo nao resolve (ex.: cwd inesperado no worker)."""
    return (_workspace_root() / "models" / "sls_spoofing").resolve()


def _candidate_model_dirs() -> list[Path]:
    env = os.environ.get("SLS_SPOOFING_MODELS_DIR", "").strip()
    candidates: list[Path] = []
    if env:
        candidates.append(Path(env).resolve())
    primary = _models_dir()
    candidates.append(primary)
    fallback = _fallback_models_dir()
    if fallback != primary:
        candidates.append(fallback)
    return candidates


def resolve_xlsr_weights_path() -> Optional[Path]:
    env = os.environ.get("SLS_XLSR_WEIGHTS", "").strip()
    if env and Path(env).is_file():
        return Path(env).resolve()
    for directory in _candidate_model_dirs():
        path = directory / XLSR_WEIGHTS_NAME
        if path.is_file():
            return path.resolve()
    vendor = _vendor_root() / XLSR_WEIGHTS_NAME
    if vendor.is_file():
        return vendor.resolve()
    return None


def resolve_sls_checkpoint_path() -> Optional[Path]:
    env = os.environ.get("SLS_SPOOFING_CHECKPOINT", "").strip()
    if env and Path(env).is_file():
        return Path(env).resolve()
    for directory in _candidate_model_dirs():
        direct = directory / "weights" / SLS_CHECKPOINT_NAME
        if direct.is_file():
            return direct.resolve()
        alt = directory / SLS_CHECKPOINT_NAME
        if alt.is_file():
            return alt.resolve()
    return None


def bootstrap_fairseq() -> None:
    """Insert vendored fairseq/SLS paths and ensure xlsr weights are discoverable."""
    global _FAIRSEQ_BOOTSTRAPPED
    if _FAIRSEQ_BOOTSTRAPPED:
        return

    fairseq_root = _fairseq_root()
    vendor_root = _vendor_root()
    if not fairseq_root.is_dir():
        raise RuntimeError(f"fairseq vendored nao encontrado em {fairseq_root}")

    for path in (fairseq_root, vendor_root):
        path_str = str(path)
        if path_str not in sys.path:
            sys.path.insert(0, path_str)

    xlsr = resolve_xlsr_weights_path()
    if xlsr is None:
        raise RuntimeError("Pesos XLS-R (xlsr2_300m.pt) nao encontrados")

    vendor_xlsr = vendor_root / XLSR_WEIGHTS_NAME
    if not vendor_xlsr.exists():
        try:
            vendor_xlsr.symlink_to(xlsr)
        except OSError:
            pass

    _FAIRSEQ_BOOTSTRAPPED = True


def runtime_status() -> Tuple[bool, str]:
    if not _fairseq_root().is_dir():
        return False, "Vendor SLS/fairseq ausente (Legados/audio/SLSforASVspoof-2021-DF)"
    if resolve_xlsr_weights_path() is None:
        return False, "Pesos XLS-R ausentes (models/sls_spoofing/xlsr2_300m.pt)"
    if resolve_sls_checkpoint_path() is None:
        return False, "Checkpoint SLS ausente (models/sls_spoofing/weights/MMpaper_model.pth)"
    try:
        bootstrap_fairseq()
        import fairseq  # noqa: F401
    except Exception as exc:
        return False, f"fairseq/SLS indisponivel: {exc}"
    return True, ""
