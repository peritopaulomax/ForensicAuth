"""Runtime probes and model path resolution for synthetic image detection."""

from __future__ import annotations

from forensics.paths import workspace_root

import os
from functools import lru_cache
from pathlib import Path
from typing import Optional, Tuple

from core.technique_ids import SYNTHETIC_IMAGE_DETECTION

MODEL1_XGB_NAME = "model1_xgboost_1p_20250809_213811.json"
MODEL2_XGB_NAME = "model2_xgboost_1p_20250809_213811.json"
NPR_WEIGHTS_NAME = "model_epoch_last_3090.pth"

HF_MODEL_IDS = (
    "haywoodsloan/ai-image-detector-deploy",
    "cmckinle/sdxl-flux-detector_v1.1",
)

_MODELS_SUBDIR = SYNTHETIC_IMAGE_DETECTION
_LEGACY_MODELS_SUBDIR = "sepael"


def _backend_root() -> Path:
    from forensics.paths import backend_root

    return backend_root()


def _workspace_root() -> Path:
    return workspace_root()


def _models_dir() -> Path:
    from app.config import get_settings

    return Path(get_settings().MODELS_DIR)


def _candidate_dirs() -> list[Path]:
    env_path = (
        os.environ.get("SYNTHETIC_IMAGE_DETECTION_MODELS_DIR")
        or os.environ.get("SEPAEL_MODELS_DIR")
    )
    candidates: list[Path] = []
    if env_path:
        candidates.append(Path(env_path))
    candidates.append(_models_dir() / _MODELS_SUBDIR)
    candidates.append(_models_dir() / _LEGACY_MODELS_SUBDIR)
    return candidates


def resolve_models_dir() -> Optional[Path]:
    """Return the first directory containing required ensemble weight files."""
    for directory in _candidate_dirs():
        if not directory.is_dir():
            continue
        if (directory / MODEL1_XGB_NAME).is_file():
            return directory.resolve()
    return None


def _resolve_models_path(path: Path) -> Path:
    if path.is_absolute():
        return path.resolve()
    if path.exists():
        return path.resolve()
    return (_backend_root() / path).resolve()


def _cache_has_hf_models(cache: Path) -> bool:
    resolved = _resolve_models_path(cache)
    return all((resolved / _hf_cache_folder(model_id)).is_dir() for model_id in HF_MODEL_IDS)


def huggingface_cache_dir() -> Path:
    env_cache = os.environ.get("HF_HUB_CACHE") or os.environ.get("TRANSFORMERS_CACHE")
    if env_cache:
        env_path = Path(env_cache)
        if _cache_has_hf_models(env_path):
            return _resolve_models_path(env_path)
    for sub in (_MODELS_SUBDIR, _LEGACY_MODELS_SUBDIR):
        custom = _models_dir() / sub / "huggingface"
        if _cache_has_hf_models(custom):
            return _resolve_models_path(custom)
    return _resolve_models_path(_models_dir() / "huggingface")


def _hf_cache_folder(model_id: str) -> str:
    return "models--" + model_id.replace("/", "--")


def resolve_hf_snapshot_path(model_id: str) -> Path:
    """Resolve a local HuggingFace snapshot directory for offline loading."""
    cache = huggingface_cache_dir()
    folder = cache / _hf_cache_folder(model_id)
    if not folder.is_dir():
        raise FileNotFoundError(f"Cache HF ausente para {model_id} em {folder}")

    refs_main = folder / "refs" / "main"
    if refs_main.is_file():
        revision = refs_main.read_text(encoding="utf-8").strip()
        snapshot = folder / "snapshots" / revision
        if snapshot.is_dir():
            return snapshot.resolve()

    snapshots_dir = folder / "snapshots"
    if snapshots_dir.is_dir():
        candidates = sorted(
            (p for p in snapshots_dir.iterdir() if p.is_dir()),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if candidates:
            return candidates[0].resolve()

    raise FileNotFoundError(f"Snapshot HF nao encontrado para {model_id} em {folder}")


def huggingface_models_cached() -> tuple[bool, str]:
    """Verify both HuggingFace models are present in the local cache."""
    cache = huggingface_cache_dir()
    missing: list[str] = []
    for model_id in HF_MODEL_IDS:
        folder = cache / _hf_cache_folder(model_id)
        if not folder.is_dir():
            missing.append(model_id)
            continue
        snapshots = folder / "snapshots"
        if not snapshots.is_dir() or not any(snapshots.iterdir()):
            missing.append(model_id)
    if missing:
        return (
            False,
            "Cache HuggingFace incompleto para: "
            + ", ".join(missing)
            + f". Esperado em {cache}/",
        )
    return True, ""


@lru_cache(maxsize=1)
def _deps_status() -> Tuple[bool, str]:
    missing: list[str] = []
    for module in ("torch", "torchvision", "transformers", "xgboost", "cv2", "skimage"):
        try:
            __import__(module)
        except ImportError:
            missing.append(module)
    if missing:
        return (
            False,
            "Detecção de imagens sintéticas requer PyTorch, torchvision, transformers, "
            "xgboost, OpenCV e scikit-image. Instale: pip install -r requirements-gpu.txt",
        )
    return True, ""


SYNTHETIC_ANALYSIS_AI_IMAGE_DETECTOR = "ai_image_detector_deploy"
SYNTHETIC_ANALYSIS_SDXL_FLUX = "sdxl_flux_detector_v1_1"
SYNTHETIC_ANALYSIS_BFREE = "bfree"
SYNTHETIC_ANALYSIS_CORVI2023 = "corvi2023"
SYNTHETIC_ANALYSIS_SAFE = "safe"

DETECTOR_DISPLAY = {
    SYNTHETIC_ANALYSIS_AI_IMAGE_DETECTOR: "ai-image-detector-deploy",
    SYNTHETIC_ANALYSIS_SDXL_FLUX: "sdxl-flux-detector v1.1",
    SYNTHETIC_ANALYSIS_BFREE: "B-Free / Bias-free",
    SYNTHETIC_ANALYSIS_CORVI2023: "DMImageDetection (Corvi2023)",
    SYNTHETIC_ANALYSIS_SAFE: "SAFE (KDD 2025)",
}

DETECTOR_CATALOG = [
    {
        "id": SYNTHETIC_ANALYSIS_AI_IMAGE_DETECTOR,
        "label": DETECTOR_DISPLAY[SYNTHETIC_ANALYSIS_AI_IMAGE_DETECTOR],
        "description": (
            "Classificador Hugging Face (ViT) treinado para distinguir imagens "
            "artificiais de reais; usado como detector CNN de propósito geral no ensemble."
        ),
        "paper_title": "haywoodsloan/ai-image-detector-deploy (model card)",
        "paper_url": "https://huggingface.co/haywoodsloan/ai-image-detector-deploy",
        "repo_url": "https://huggingface.co/haywoodsloan/ai-image-detector-deploy",
    },
    {
        "id": SYNTHETIC_ANALYSIS_SDXL_FLUX,
        "label": DETECTOR_DISPLAY[SYNTHETIC_ANALYSIS_SDXL_FLUX],
        "description": (
            "Detector Hugging Face focado em gerações SDXL/FLUX; "
            "complementa o ensemble em difusão moderna."
        ),
        "paper_title": "cmckinle/sdxl-flux-detector_v1.1 (model card)",
        "paper_url": "https://huggingface.co/cmckinle/sdxl-flux-detector_v1.1",
        "repo_url": "https://huggingface.co/cmckinle/sdxl-flux-detector_v1.1",
    },
    {
        "id": SYNTHETIC_ANALYSIS_BFREE,
        "label": DETECTOR_DISPLAY[SYNTHETIC_ANALYSIS_BFREE],
        "description": (
            "Paradigma bias-free (CVPR 2025): fakes gerados a partir de reais via "
            "condicionamento Stable Diffusion, com ViT/DINOv2 e crops 504×504."
        ),
        "paper_title": (
            "A Bias-Free Training Paradigm for More General AI-generated Image Detection"
        ),
        "paper_url": "https://arxiv.org/abs/2412.17671",
        "repo_url": "https://github.com/grip-unina/B-Free",
    },
    {
        "id": SYNTHETIC_ANALYSIS_CORVI2023,
        "label": DETECTOR_DISPLAY[SYNTHETIC_ANALYSIS_CORVI2023],
        "description": (
            "Detector ResNet50 (GRIP-UNINA) para imagens de modelos de difusão; "
            "inferência em tiles 1024px com LLR>0 → sintético."
        ),
        "paper_title": (
            "On The Detection of Synthetic Images Generated by Diffusion Models (ICASSP 2023)"
        ),
        "paper_url": "https://arxiv.org/abs/2211.00680",
        "repo_url": "https://github.com/grip-unina/DMimageDetection",
    },
    {
        "id": SYNTHETIC_ANALYSIS_SAFE,
        "label": DETECTOR_DISPLAY[SYNTHETIC_ANALYSIS_SAFE],
        "description": (
            "SAFE (KDD 2025): crop em vez de downsampling, ColorJitter/rotação e "
            "máscara de patches para generalização SID; eval com CenterCrop 256×256."
        ),
        "paper_title": (
            "Improving Synthetic Image Detection Towards Generalization: "
            "An Image Transformation Perspective"
        ),
        "paper_url": "https://arxiv.org/abs/2408.06741",
        "repo_url": "https://github.com/Ouxiang-Li/SAFE",
    },
]


def _hf_model_cached(model_id: str) -> Tuple[bool, str]:
    cache = huggingface_cache_dir()
    folder = cache / _hf_cache_folder(model_id)
    if not folder.is_dir():
        return False, f"Cache HuggingFace ausente para {model_id} (esperado em {cache}/)"
    snapshots = folder / "snapshots"
    if not snapshots.is_dir() or not any(snapshots.iterdir()):
        return False, f"Snapshots HuggingFace incompletos para {model_id}"
    return True, ""


def detector_runtime_status(detector_id: str) -> Tuple[bool, str]:
    """Per-detector availability for the synthetic-image ensemble UI."""
    ok, reason = _deps_status()
    if not ok:
        return False, reason

    if detector_id == SYNTHETIC_ANALYSIS_AI_IMAGE_DETECTOR:
        return _hf_model_cached(HF_MODEL_IDS[0])
    if detector_id == SYNTHETIC_ANALYSIS_SDXL_FLUX:
        return _hf_model_cached(HF_MODEL_IDS[1])
    if detector_id == SYNTHETIC_ANALYSIS_BFREE:
        from forensics.bfree.bfree_runtime import bfree_runtime_status

        return bfree_runtime_status()
    if detector_id == SYNTHETIC_ANALYSIS_CORVI2023:
        from forensics.truebees_clip_d.clipd_pipeline import CORVI2023_MODEL_NAME
        from forensics.truebees_clip_d.clipd_runtime import clipd_runtime_status

        return clipd_runtime_status(CORVI2023_MODEL_NAME)
    if detector_id == SYNTHETIC_ANALYSIS_SAFE:
        from forensics.safe.safe_runtime import safe_runtime_status

        return safe_runtime_status()
    return False, f"Detector desconhecido: {detector_id}"


def runtime_status() -> Tuple[bool, str]:
    """Return (available, reason). reason is empty when the technique can run."""
    ok, reason = _deps_status()
    if not ok:
        return False, reason

    models_dir = resolve_models_dir()
    if models_dir is None:
        expected = _models_dir() / _MODELS_SUBDIR
        return (
            False,
            "Pesos do ensemble de detecção de imagens sintéticas não encontrados. Copie "
            f"{MODEL1_XGB_NAME} para {expected}/ ou defina SYNTHETIC_IMAGE_DETECTION_MODELS_DIR.",
        )

    hf_ok, hf_reason = huggingface_models_cached()
    if not hf_ok:
        return False, hf_reason

    return True, ""