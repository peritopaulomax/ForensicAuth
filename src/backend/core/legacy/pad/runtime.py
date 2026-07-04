"""Runtime availability probe for Presentation Attack Detection (PAD)."""

from __future__ import annotations

from pathlib import Path
from typing import Tuple


def _workspace_root() -> Path:
    """Project root inferred from this file's location."""
    return Path(__file__).resolve().parents[5]


def pad_models_dir() -> Path:
    """Return the absolute path to the PAD models directory."""
    return (_workspace_root() / "models" / "pad").resolve()


def pad_runtime_status() -> Tuple[bool, str]:
    """Return (available, reason) for the PAD plugin.

    Requires the vendored Silent-Face-Anti-Spoofing weights under
    ``models/pad/anti_spoof_models`` and the RetinaFace detector under
    ``models/pad/detection_model``.
    """
    base = pad_models_dir()
    anti_spoof = base / "anti_spoof_models"
    detection = base / "detection_model"

    if not anti_spoof.is_dir():
        return False, f"Diretorio de modelos PAD nao encontrado: {anti_spoof}"
    if not detection.is_dir():
        return False, f"Diretorio do detector de faces PAD nao encontrado: {detection}"

    model_files = list(anti_spoof.glob("*.pth"))
    if not model_files:
        return False, f"Nenhum modelo .pth encontrado em {anti_spoof}"

    deploy = detection / "deploy.prototxt"
    caffemodel = detection / "Widerface-RetinaFace.caffemodel"
    if not deploy.is_file() or not caffemodel.is_file():
        return False, f"Arquivos do detector RetinaFace incompletos em {detection}"

    return True, ""
