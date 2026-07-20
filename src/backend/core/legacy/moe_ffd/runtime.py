"""Runtime availability + checkpoint integrity for MoE-FFD."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Tuple

# Gates oficiais nascem em zeros; um checkpoint treinado deve tê-las longe disso.
_GATE_ABSMAX_MIN = float(os.environ.get("MOE_FFD_GATE_ABSMAX_MIN", "1e-8"))
# Head binarya fraco demais também indica weights sem treino útil.
_HEAD_ABSMAX_MIN = float(os.environ.get("MOE_FFD_HEAD_ABSMAX_MIN", "0.1"))


def _workspace_root() -> Path:
    return Path(__file__).resolve().parents[5]


def moe_ffd_vendor_dir() -> Path:
    override = os.environ.get("MOE_FFD_VENDOR_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return (_workspace_root() / "vendor" / "MoE-FFD").resolve()


def moe_ffd_checkpoint_path() -> Path:
    override = os.environ.get("MOE_FFD_CHECKPOINT")
    if override:
        return Path(override).expanduser().resolve()
    return (_workspace_root() / "models" / "moe_ffd" / "MoE-FFD.tar").resolve()


def _checkpoint_stamp(path: Path) -> Tuple[str, int, int]:
    st = path.stat()
    return (str(path.resolve()), int(st.st_mtime_ns), int(st.st_size))


@lru_cache(maxsize=4)
def _inspect_checkpoint_cached(stamp: Tuple[str, int, int]) -> Dict[str, Any]:
    """Load checkpoint once per (path,mtime,size) and return health report."""
    path = Path(stamp[0])
    import torch

    try:
        obj = torch.load(str(path), map_location="cpu", weights_only=False)
    except TypeError:
        obj = torch.load(str(path), map_location="cpu")

    report: Dict[str, Any] = {
        "path": str(path),
        "format": "unknown",
        "epoch": None,
        "has_optimizer": False,
        "n_keys": 0,
        "gate_absmax": None,
        "noise_absmax": None,
        "head_weight_absmax": None,
        "ok": False,
        "reason": "",
    }

    if isinstance(obj, dict) and "model_state_dict" in obj:
        sd = obj["model_state_dict"]
        report["format"] = "training_tar"  # models_params_{epoch}.tar
        report["epoch"] = obj.get("epoch")
        report["has_optimizer"] = "optimizer_state_dict" in obj
    elif isinstance(obj, dict) and "state_dict" in obj:
        sd = obj["state_dict"]
        report["format"] = "wrapped_state_dict"
        report["epoch"] = obj.get("epoch")
    elif isinstance(obj, dict) and any(k.startswith("blocks.") for k in obj):
        sd = obj
        report["format"] = "raw_state_dict"  # model_params_best_*.pkl
    else:
        report["reason"] = (
            f"Checkpoint MoE-FFD com formato inesperado em {path}. "
            "Esperado model_state_dict (train.tar) ou state_dict puro (best.pkl)."
        )
        return report

    if not isinstance(sd, dict) or not sd:
        report["reason"] = f"Checkpoint MoE-FFD sem pesos utilisaveis: {path}"
        return report

    report["n_keys"] = len(sd)

    def _absmax(substr: str) -> float:
        vals = [float(v.detach().abs().max()) for k, v in sd.items() if substr in k and hasattr(v, "abs")]
        return max(vals) if vals else 0.0

    gate_absmax = _absmax("w_gate")
    noise_absmax = _absmax("w_noise")
    head_absmax = 0.0
    if "head.weight" in sd:
        head_absmax = float(sd["head.weight"].detach().abs().max())

    report["gate_absmax"] = gate_absmax
    report["noise_absmax"] = noise_absmax
    report["head_weight_absmax"] = head_absmax

    # Causas forenses tipicas do HF/Baidu MoE-FFD.tar (epoch 14, gates ~0):
    if gate_absmax < _GATE_ABSMAX_MIN:
        report["ok"] = False
        report["reason"] = (
            "Checkpoint MoE-FFD INVALIDO para uso forense: gates MoE (w_gate) "
            f"ainda em zeros (absmax={gate_absmax:.3g}, limiar={_GATE_ABSMAX_MIN:g}). "
            f"Arquivo parece mid-training (format={report['format']}, epoch={report['epoch']}), "
            "nao o model_params_best_*.pkl do paper. "
            "Com estes pesos o detector colapsa em 'real' para faces. "
            "Obtenha o best.pkl oficial (Baidu/HF) ou pesagem corretamente treinada; "
            "veja vendor/MoE-FFD/train.py (salva best quando AUC sobe)."
        )
        return report

    if head_absmax < _HEAD_ABSMAX_MIN and report["format"] == "training_tar":
        report["ok"] = False
        report["reason"] = (
            "Checkpoint MoE-FFD suspeito: head.weight absmax "
            f"{head_absmax:.4f} < {_HEAD_ABSMAX_MIN} e formato training_tar "
            f"(epoch={report['epoch']}). Prefira model_params_best_*.pkl."
        )
        return report

    report["ok"] = True
    report["reason"] = ""
    return report


def inspect_moe_ffd_checkpoint(path: Path | None = None) -> Dict[str, Any]:
    """Return integrity report for the configured (or given) checkpoint."""
    ckpt = Path(path) if path is not None else moe_ffd_checkpoint_path()
    if not ckpt.is_file():
        return {
            "path": str(ckpt),
            "ok": False,
            "reason": f"Checkpoint ausente: {ckpt}",
            "format": None,
            "epoch": None,
            "gate_absmax": None,
        }
    return dict(_inspect_checkpoint_cached(_checkpoint_stamp(ckpt)))


def clear_checkpoint_inspect_cache() -> None:
    _inspect_checkpoint_cached.cache_clear()


def moe_ffd_runtime_status() -> Tuple[bool, str]:
    """Return (available, reason). Paths + RetinaFace + checkpoint integrity."""
    vendor = moe_ffd_vendor_dir()
    vit_moe = vendor / "ViT_MoE.py"
    if not vit_moe.is_file():
        return False, f"Vendor MoE-FFD ausente (esperado {vit_moe})"

    ckpt = moe_ffd_checkpoint_path()
    if not ckpt.is_file():
        return (
            False,
            f"Checkpoint MoE-FFD ausente: {ckpt}. "
            "Execute scripts/download_moe_ffd_weights.py",
        )
    if ckpt.stat().st_size < 1_000_000:
        return False, f"Checkpoint MoE-FFD parece incompleto: {ckpt}"

    from core.legacy.moe_ffd.face_crop import retinaface_available

    ok_rf, reason_rf = retinaface_available()
    if not ok_rf:
        return False, reason_rf

    health = inspect_moe_ffd_checkpoint(ckpt)
    if not health.get("ok"):
        return False, str(health.get("reason") or "Checkpoint MoE-FFD invalido")

    return True, ""
