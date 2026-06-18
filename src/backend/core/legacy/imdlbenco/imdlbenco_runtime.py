"""Runtime probes for IMDL-BenCo hub methods."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from core.legacy.imdlbenco.imdlbenco_catalog import (
    IMDLBENCO_METHODS,
    MethodStatus,
    get_method,
)

CHECKPOINT_NAMES = {
    "trufor": "trufor_casiav2.pth",
    "cat_net": "cat_net_cat_net.pth",
    "objectformer": "object_former_casiav2.pth",
    "sparse_vit": "sparse_vit.pth",
}

TRUFOR_AUX_FILES = ("noiseprint.pth", "mit_b2.pth")
OBJECTFORMER_INIT = "processed_model_weights.pth"

MESORCH_VARIANTS = {
    "standard": "mesorch-98.pth",
    "mesorch_p": "mesorch_p-118.pth",
}

MESORCH_DRIVE_FOLDER = "1jwYv-S3HAZqzz0YxM9bJynBiPv-O9-6x"
TRUFOR_DRIVE_FOLDER = "1Q9RxEHsIcRWeZjJRBtAwW4au5QybIoP2"

DINOV3_IML_VENDOR_DIR = "DINOv3-IML"
DINOV3_BACKBONE_VENDOR_DIR = "dinov3"
DINOV3_IML_CHECKPOINT_NAMES = ("cat_vitl_lora_r32.pth", "checkpoint-48.pth")
DINOV3_IML_MIN_CHECKPOINT_BYTES = 100_000_000

CO_TRANSFORMERS_VENDOR_DIR = "Co-Transformers-main"
CO_TRANSFORMERS_CHECKPOINT_NAMES = ("co_transformers.pth",)
CO_TRANSFORMERS_MIN_CHECKPOINT_BYTES = 50_000_000

VENDOR_DIRS = {
    "dinov3_iml": DINOV3_IML_VENDOR_DIR,
    "co_transformers": "Co-Transformers-main",
    "nfa_vit": "BR-Gen-main",
    "forensic_hub": "ForensicHub-main",
    "opensdi": "OpenSDI-main",
    "miml_apscnet": "MIML",
}

NFA_VIT_INIT_FILES = {
    "noiseprint": "noiseprint.pth",
    "seg_b0": "segformer_b0_backbone_weights.pth",
    "seg_b2": "segformer_b2_backbone_weights.pth",
}
NFA_VIT_CHECKPOINT_NAME = "nfa_vit_brgen.pth"
NFA_VIT_MIN_CHECKPOINT_BYTES = 1_000_000
NFA_VIT_MIN_INIT_BYTES = 10_000

MIML_APSC_CHECKPOINT_NAME = "APSC-Net.pth"
MIML_MIN_CHECKPOINT_BYTES = 100_000_000


def _legacy_root() -> Path:
    return Path(__file__).resolve().parent


def _workspace_root() -> Path:
    return Path(__file__).resolve().parents[5]


def imdlbenco_models_dir() -> Path:
    env = os.environ.get("IMDLBENCO_MODELS_DIR")
    if env:
        return Path(env).resolve()
    from app.config import get_settings

    return (Path(get_settings().MODELS_DIR) / "imdlbenco").resolve()


def vendor_root() -> Path:
    env = os.environ.get("IMDLBENCO_VENDOR_DIR")
    if env:
        return Path(env).resolve()
    return (_workspace_root() / "vendor").resolve()


def miml_vendor_root() -> Path:
    return vendor_root() / "MIML"


def miml_iml_vendor_root() -> Path:
    return miml_vendor_root() / "models for IML"


def miml_models_dir() -> Path:
    return imdlbenco_models_dir() / "miml"


def miml_apsc_models_dir() -> Path:
    return miml_models_dir() / "apsc"


def resolve_miml_apsc_checkpoint() -> Path | None:
    path = miml_apsc_models_dir() / MIML_APSC_CHECKPOINT_NAME
    if path.is_file() and path.stat().st_size >= MIML_MIN_CHECKPOINT_BYTES:
        return path
    return None


def dinov3_iml_vendor_root() -> Path:
    return vendor_root() / DINOV3_IML_VENDOR_DIR


def dinov3_backbone_repo() -> Path:
    return vendor_root() / DINOV3_BACKBONE_VENDOR_DIR


def dinov3_iml_models_dir() -> Path:
    return imdlbenco_models_dir() / "dinov3_iml"


def co_transformers_vendor_root() -> Path:
    return vendor_root() / CO_TRANSFORMERS_VENDOR_DIR


def co_transformers_models_dir() -> Path:
    return imdlbenco_models_dir() / "co_transformers"


def resolve_co_transformers_segformer_pretrain() -> Path | None:
    local = co_transformers_models_dir() / "mit_b3.pth"
    if local.is_file() and local.stat().st_size > 1_000_000:
        return local
    return resolve_segformer_pretrain()


def resolve_co_transformers_noiseprint() -> Path | None:
    local = co_transformers_models_dir() / "noiseprint.pth"
    if local.is_file() and local.stat().st_size > 10_000:
        try:
            import torch

            obj = torch.load(str(local), map_location="cpu", weights_only=False)
            if isinstance(obj, dict) and "model" not in obj:
                keys = list(obj.keys())
                if keys and keys[0].startswith("0."):
                    return local
        except Exception:
            pass
    gdrive = co_transformers_models_dir() / "_gdrive" / "pretrained" / "noiseprint.pth"
    if gdrive.is_file() and gdrive.stat().st_size > 10_000:
        return gdrive
    return None


def resolve_co_transformers_checkpoint() -> Path | None:
    base = co_transformers_models_dir()
    for fname in CO_TRANSFORMERS_CHECKPOINT_NAMES:
        path = base / fname
        if path.is_file() and path.stat().st_size >= CO_TRANSFORMERS_MIN_CHECKPOINT_BYTES:
            return path
    candidates = sorted(base.glob("checkpoint-*.pth"), key=lambda p: p.name, reverse=True)
    for path in candidates:
        if path.is_file() and path.stat().st_size >= CO_TRANSFORMERS_MIN_CHECKPOINT_BYTES:
            return path
    return None


def resolve_dinov3_iml_checkpoint() -> Path | None:
    base = dinov3_iml_models_dir()
    for fname in DINOV3_IML_CHECKPOINT_NAMES:
        path = base / fname
        if path.is_file() and path.stat().st_size >= DINOV3_IML_MIN_CHECKPOINT_BYTES:
            return path
    candidates = sorted(base.glob("checkpoint-*.pth"), key=lambda p: p.name, reverse=True)
    for path in candidates:
        if path.is_file() and path.stat().st_size >= DINOV3_IML_MIN_CHECKPOINT_BYTES:
            return path
    return None


def resolve_trufor_config() -> Path:
    return _legacy_root() / "configs" / "trufor.yaml"


def resolve_cat_net_config() -> Path:
    return _legacy_root() / "configs" / "CAT_full.yaml"


def resolve_mesorch_checkpoint(variant: str = "standard") -> Path | None:
    fname = MESORCH_VARIANTS.get(variant) or MESORCH_VARIANTS["standard"]
    path = imdlbenco_models_dir() / "mesorch" / fname
    if path.is_file() and path.stat().st_size > 100_000:
        return path
    return None


def list_mesorch_variants() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for variant_id, fname in MESORCH_VARIANTS.items():
        path = imdlbenco_models_dir() / "mesorch" / fname
        ready = path.is_file() and path.stat().st_size > 100_000
        label = "Mesorch" if variant_id == "standard" else "Mesorch-P"
        out.append(
            {
                "id": variant_id,
                "label": label,
                "filename": fname,
                "ready": ready,
                "path": str(path) if ready else None,
            }
        )
    return out


def resolve_checkpoint(method_id: str, *, mesorch_variant: str = "standard") -> Path | None:
    if get_method(method_id) is None:
        return None

    if method_id == "mesorch":
        return resolve_mesorch_checkpoint(mesorch_variant)

    fname = CHECKPOINT_NAMES.get(method_id)
    if not fname:
        return None

    path = imdlbenco_models_dir() / method_id / fname
    if path.is_file() and path.stat().st_size > 100_000:
        return path
    return None


def resolve_trufor_aux(name: str) -> Path | None:
    path = imdlbenco_models_dir() / "trufor" / name
    if path.is_file() and path.stat().st_size > 1_000:
        return path
    return None


def resolve_objectformer_init() -> Path | None:
    path = imdlbenco_models_dir() / "objectformer" / OBJECTFORMER_INIT
    if path.is_file() and path.stat().st_size > 100_000:
        return path
    return None


def resolve_segformer_pretrain() -> Path | None:
    path = imdlbenco_models_dir() / "mesorch" / "mit_b3.pth"
    if path.is_file():
        return path
    return None


def resolve_uniformer_pretrain() -> Path | None:
    path = imdlbenco_models_dir() / "sparse_vit" / "uniformer_base_in1k.pth"
    if path.is_file():
        return path
    return None


def nfa_vit_models_dir() -> Path:
    return imdlbenco_models_dir() / "nfa_vit"


def resolve_nfa_vit_init_weight(key: str) -> Path | None:
    fname = NFA_VIT_INIT_FILES.get(key)
    if not fname:
        return None
    path = nfa_vit_models_dir() / fname
    if path.is_file() and path.stat().st_size >= NFA_VIT_MIN_INIT_BYTES:
        return path
    return None


def resolve_nfa_vit_checkpoint() -> Path | None:
    base = nfa_vit_models_dir()
    preferred = base / NFA_VIT_CHECKPOINT_NAME
    if preferred.is_file() and preferred.stat().st_size >= NFA_VIT_MIN_CHECKPOINT_BYTES:
        return preferred
    candidates = sorted(base.glob("checkpoint-*.pth"), key=lambda p: p.name, reverse=True)
    for path in candidates:
        if path.is_file() and path.stat().st_size >= NFA_VIT_MIN_CHECKPOINT_BYTES:
            return path
    return None


def _package_ok() -> tuple[bool, str]:
    try:
        import IMDLBenCo  # noqa: F401
    except ImportError:
        return False, "Pacote 'imdlbenco' ausente. Execute: pip install imdlbenco"
    try:
        import timm  # noqa: F401
    except ImportError:
        return False, "Dependencia 'timm' ausente."
    return True, ""


def _trufor_ready() -> tuple[bool, str]:
    from core.legacy.imdlbenco.trufor_official_pipeline import official_runtime_ready

    return official_runtime_ready()


def _objectformer_ready() -> tuple[bool, str]:
    ckpt = resolve_checkpoint("objectformer")
    init = resolve_objectformer_init()
    if ckpt is None or init is None:
        missing = []
        if ckpt is None:
            missing.append(CHECKPOINT_NAMES["objectformer"])
        if init is None:
            missing.append(OBJECTFORMER_INIT)
        return (
            False,
            f"Pesos ObjectFormer ausentes ({', '.join(missing)}). "
            "Execute: python scripts/download_imdlbenco_weights.py",
        )
    return True, ""


def method_runtime_status(method_id: str) -> tuple[MethodStatus, str]:
    spec = get_method(method_id)
    if spec is None:
        return "unavailable", f"Metodo desconhecido: {method_id}"

    if method_id == "dinov3_iml":
        from core.legacy.imdlbenco.dinov3_iml_official_pipeline import official_runtime_ready

        ok, reason = official_runtime_ready()
        return ("ready", "") if ok else ("weights_missing", reason)

    if method_id == "co_transformers":
        from core.legacy.imdlbenco.co_transformers_official_pipeline import official_runtime_ready

        ok, reason = official_runtime_ready()
        return ("ready", "") if ok else ("weights_missing", reason)

    if method_id == "miml_apscnet":
        from core.legacy.imdlbenco.miml_official_pipeline import official_runtime_ready

        ok, reason = official_runtime_ready(method_id)
        return ("ready", "") if ok else ("weights_missing", reason)

    if spec.tier == "ecosystem" and method_id not in (
        "nfa_vit",
        "co_transformers",
        "miml_apscnet",
    ):
        vendor_name = VENDOR_DIRS.get(method_id)
        if vendor_name and not (vendor_root() / vendor_name).is_dir():
            return (
                "vendor_missing",
                f"Repositorio externo ausente em vendor/{vendor_name}. "
                f"Clone: {spec.repo_url}",
            )
        return (
            "weights_missing",
            f"Inferencia para {spec.name} ainda nao integrada neste build.",
        )

    if method_id == "nfa_vit":
        from core.legacy.imdlbenco.nfa_vit_official_pipeline import official_runtime_ready

        ok, reason = official_runtime_ready()
        return ("ready", "") if ok else ("weights_missing", reason)

    ok_pkg, pkg_reason = _package_ok()
    if not ok_pkg:
        return "unavailable", pkg_reason

    if method_id == "trufor":
        ok, reason = _trufor_ready()
        return ("ready", "") if ok else ("weights_missing", reason)

    if method_id == "objectformer":
        ok, reason = _objectformer_ready()
        return ("ready", "") if ok else ("weights_missing", reason)

    if method_id == "mesorch":
        from core.legacy.imdlbenco.mesorch_official_pipeline import official_runtime_ready

        variants = list_mesorch_variants()
        if not any(v["ready"] for v in variants):
            missing = ", ".join(v["filename"] for v in variants)
            return (
                "weights_missing",
                f"Pesos Mesorch ausentes ({missing}). "
                "Execute: python scripts/download_imdlbenco_weights.py",
            )
        ok_std, reason_std = official_runtime_ready(mesorch_variant="standard")
        if ok_std:
            return "ready", ""
        ok_p, reason_p = official_runtime_ready(mesorch_variant="mesorch_p")
        if ok_p:
            return "ready", ""
        return "weights_missing", reason_std or reason_p

    if resolve_checkpoint(method_id) is None:
        return (
            "weights_missing",
            f"Pesos ausentes para {spec.name}. Execute: python scripts/download_imdlbenco_weights.py",
        )

    if method_id == "sparse_vit" and resolve_uniformer_pretrain() is None:
        return (
            "weights_missing",
            "Backbone Uniformer ausente em models/imdlbenco/sparse_vit/.",
        )

    if method_id == "cat_net":
        from core.legacy.imdlbenco.cat_net_official_pipeline import official_runtime_ready

        ok, reason = official_runtime_ready()
        return ("ready", "") if ok else ("weights_missing", reason)

    return "ready", ""


@lru_cache(maxsize=1)
def imdlbenco_runtime_status() -> tuple[bool, str]:
    ok_pkg, reason = _package_ok()
    if not ok_pkg:
        return False, reason
    ready = [m.id for m in IMDLBENCO_METHODS if method_runtime_status(m.id)[0] == "ready"]
    if not ready:
        return (
            False,
            "Nenhum metodo IMDL-BenCo pronto. Instale pesos: python scripts/download_imdlbenco_weights.py",
        )
    return True, ""


def list_method_status() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for method in IMDLBENCO_METHODS:
        status, reason = method_runtime_status(method.id)
        out.append(
            {
                "id": method.id,
                "name": method.name,
                "venue": method.venue,
                "tier": method.tier,
                "description": method.description,
                "repo_url": method.repo_url,
                "stars": method.stars,
                "accent": method.accent,
                "status": status,
                "unavailable_reason": reason or None,
                "ready": status == "ready",
                "variants": list_mesorch_variants() if method.id == "mesorch" else None,
            }
        )
    return out


def clear_runtime_cache() -> None:
    imdlbenco_runtime_status.cache_clear()
