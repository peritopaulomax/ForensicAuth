"""Runtime paths and fairseq bootstrap for TFCL audio spoofing detection."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional, Tuple

from forensics.paths import workspace_root

XLSR_WEIGHTS_NAME = "xlsr2_300m.pt"
TFCL_CHECKPOINT_NAME = "TFCL_best_ckpt.pth"

_FAIRSEQ_BOOTSTRAPPED = False


def _workspace_root() -> Path:
    return workspace_root()


def _vendor_root() -> Path:
    return _workspace_root() / "vendor" / "tfcl"


def _fairseq_root() -> Path:
    # Same pinned fairseq commit as SLS / SSL_Anti-spoofing.
    return (
        _workspace_root()
        / "vendor"
        / "sls_asvspoof"
        / "fairseq-a54021305d6b3c4c5959ac9395135f63202db8f1"
    )


def _models_dir() -> Path:
    from app.config import get_settings

    return (Path(get_settings().MODELS_DIR) / "tfcl").resolve()


def _fallback_models_dir() -> Path:
    return (_workspace_root() / "models" / "tfcl").resolve()


def _candidate_model_dirs() -> list[Path]:
    env = os.environ.get("TFCL_MODELS_DIR", "").strip()
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
    env = os.environ.get("TFCL_XLSR_WEIGHTS", "").strip()
    if env and Path(env).is_file():
        return Path(env).resolve()
    for directory in _candidate_model_dirs():
        path = directory / XLSR_WEIGHTS_NAME
        if path.is_file():
            return path.resolve()
    # Share SLS XLS-R weights when present.
    sls = _workspace_root() / "models" / "sls_spoofing" / XLSR_WEIGHTS_NAME
    if sls.is_file():
        return sls.resolve()
    vendor = _vendor_root() / XLSR_WEIGHTS_NAME
    if vendor.is_file():
        return vendor.resolve()
    return None


def resolve_tfcl_checkpoint_path() -> Optional[Path]:
    env = os.environ.get("TFCL_CHECKPOINT", "").strip()
    if env and Path(env).is_file():
        return Path(env).resolve()
    for directory in _candidate_model_dirs():
        direct = directory / "weights" / TFCL_CHECKPOINT_NAME
        if direct.is_file():
            return direct.resolve()
        alt = directory / TFCL_CHECKPOINT_NAME
        if alt.is_file():
            return alt.resolve()
    return None


def bootstrap_tfcl() -> None:
    """Insert vendored fairseq/TFCL paths; ensure xlsr weights are discoverable."""
    global _FAIRSEQ_BOOTSTRAPPED

    fairseq_root = _fairseq_root()
    vendor_root = _vendor_root()
    if not fairseq_root.is_dir():
        raise RuntimeError(f"fairseq vendored nao encontrado em {fairseq_root}")
    if not vendor_root.is_dir():
        raise RuntimeError(f"Vendor TFCL ausente em {vendor_root}")

    # Keep TFCL ahead of other vendors that also ship a top-level ``model``.
    for path in (fairseq_root, vendor_root):
        path_str = str(path)
        if path_str in sys.path:
            sys.path.remove(path_str)
        sys.path.insert(0, path_str)

    # Drop cached ``model`` from another detector (e.g. SLS) so TFCL loads its own.
    for mod_name in list(sys.modules):
        if mod_name == "model" or mod_name.startswith("model."):
            del sys.modules[mod_name]

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
    if not _vendor_root().is_dir():
        return False, "Vendor TFCL ausente (vendor/tfcl)"
    if not _fairseq_root().is_dir():
        return False, "Vendor fairseq/SLS ausente (necessario para TFCL)"
    if resolve_xlsr_weights_path() is None:
        return False, "Pesos XLS-R ausentes (models/tfcl/xlsr2_300m.pt)"
    if resolve_tfcl_checkpoint_path() is None:
        return False, "Checkpoint TFCL ausente (models/tfcl/weights/TFCL_best_ckpt.pth)"
    try:
        bootstrap_tfcl()
        import fairseq  # noqa: F401
    except Exception as exc:
        return False, f"fairseq/TFCL indisponivel: {exc}"
    return True, ""
