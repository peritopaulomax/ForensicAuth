"""Thin inference wrapper around official MoE-FFD (vendor/MoE-FFD).

Preserves the official ViT-MoE algorithm (Regra Máxima 8). Only orchestration,
preprocess contract, RetinaFace crop, and soft compatibility with newer timm
versions live here.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import cv2
import numpy as np
import torch
import torch.nn.functional as F

from core.gpu_inference import resolve_inference_device
from core.legacy.moe_ffd.face_crop import crop_aligned_face, retinaface_available
from core.legacy.moe_ffd.runtime import moe_ffd_checkpoint_path, moe_ffd_vendor_dir

logger = logging.getLogger(__name__)

_IMG_SIZE = 224
_MEAN = (0.5, 0.5, 0.5)
_STD = (0.5, 0.5, 0.5)
_DEFAULT_FACE_MARGIN = float(os.environ.get("MOE_FFD_FACE_MARGIN", "1.3"))
_DEFAULT_FACE_CONF = float(os.environ.get("MOE_FFD_FACE_CONF", "0.6"))

_model_lock = threading.Lock()
_cached: dict[str, Any] = {"model": None, "device": None, "checkpoint": None, "epoch": None}
_transform = None


def _patch_timm_register_for_legacy_cfg() -> None:
    """MoE-FFD ViT_MoE uses legacy default_cfg key ``hf_hub``; timm≥1 expects ``hf_hub_id``."""
    try:
        import timm.models._registry as registry
    except ImportError:
        return

    if getattr(registry.register_model, "_moe_ffd_soft", False):
        return

    orig = registry.register_model

    def soft_register(fn=None):  # type: ignore[no-untyped-def]
        def deco(f):
            try:
                return orig(f)
            except TypeError as exc:
                logger.debug("Skipping MoE-FFD model registration incompatible with timm: %s", exc)
                return f

        return deco(fn) if fn is not None else deco

    soft_register._moe_ffd_soft = True  # type: ignore[attr-defined]
    registry.register_model = soft_register  # type: ignore[assignment]
    try:
        import timm.models.registry as legacy_registry

        legacy_registry.register_model = soft_register  # type: ignore[assignment]
    except Exception:
        pass


def _import_vision_transformer_cls():
    vendor = moe_ffd_vendor_dir()
    vendor_str = str(vendor)
    if vendor_str not in sys.path:
        sys.path.insert(0, vendor_str)
    _patch_timm_register_for_legacy_cfg()
    from ViT_MoE import VisionTransformer  # type: ignore

    return VisionTransformer


def _build_moe_ffd_model():
    VisionTransformer = _import_vision_transformer_cls()
    return VisionTransformer(
        img_size=_IMG_SIZE,
        patch_size=16,
        embed_dim=768,
        depth=12,
        num_heads=12,
        num_classes=2,
        representation_size=None,
    )


def _get_official_transform():
    """Exact preprocess from vendor/MoE-FFD/dataset.py (albumentations)."""
    global _transform
    if _transform is not None:
        return _transform
    import albumentations as alb
    from albumentations.pytorch.transforms import ToTensorV2

    _transform = alb.Compose(
        [
            alb.Resize(_IMG_SIZE, _IMG_SIZE),
            alb.Normalize(mean=list(_MEAN), std=list(_STD)),
            ToTensorV2(),
        ]
    )
    return _transform


def _load_rgb_uint8(image_path: str | Path) -> np.ndarray:
    """Load RGB uint8 the same way as official dataset (`cv2.imread` → BGR2RGB)."""
    path = Path(image_path)
    bgr = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if bgr is None:
        from PIL import Image

        rgb = np.asarray(Image.open(path).convert("RGB"), dtype=np.uint8)
        if rgb.ndim != 3 or rgb.shape[2] != 3:
            raise ValueError(f"Nao foi possivel carregar imagem RGB: {path}")
        return rgb
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


def _load_model(device: torch.device, checkpoint: Path):
    with _model_lock:
        if (
            _cached["model"] is not None
            and _cached["device"] == str(device)
            and _cached["checkpoint"] == str(checkpoint)
        ):
            return _cached["model"]

        model = _build_moe_ffd_model()
        try:
            checkpoint_obj = torch.load(str(checkpoint), map_location="cpu", weights_only=False)
        except TypeError:
            checkpoint_obj = torch.load(str(checkpoint), map_location="cpu")

        epoch = None
        if isinstance(checkpoint_obj, dict) and "model_state_dict" in checkpoint_obj:
            state = checkpoint_obj["model_state_dict"]
            epoch = checkpoint_obj.get("epoch")
        elif isinstance(checkpoint_obj, dict) and "state_dict" in checkpoint_obj:
            state = checkpoint_obj["state_dict"]
            epoch = checkpoint_obj.get("epoch")
        else:
            state = checkpoint_obj

        missing, unexpected = model.load_state_dict(state, strict=False)
        if missing or unexpected:
            raise RuntimeError(
                f"Checkpoint MoE-FFD incompativel com a arquitetura vendor "
                f"(missing={len(missing)} unexpected={len(unexpected)}). "
                f"Ex.: missing[:5]={missing[:5]} unexpected[:5]={unexpected[:5]}"
            )
        model.to(device)
        model.eval()
        _cached["model"] = model
        _cached["device"] = str(device)
        _cached["checkpoint"] = str(checkpoint)
        _cached["epoch"] = epoch
        return model


def preprocess_rgb_to_tensor(rgb: np.ndarray) -> torch.Tensor:
    """Official MoE-FFD albumentations contract on an RGB uint8 array."""
    tensor = _get_official_transform()(image=rgb)["image"]
    if not isinstance(tensor, torch.Tensor):
        tensor = torch.as_tensor(tensor)
    return tensor.unsqueeze(0)


def prepare_face_input(
    image_path: str | Path,
    *,
    crop_face: bool = True,
    face_margin: float = _DEFAULT_FACE_MARGIN,
    face_confidence: float = _DEFAULT_FACE_CONF,
) -> Dict[str, Any]:
    """Load image, optionally RetinaFace-crop, ready for MoE-FFD."""
    rgb = _load_rgb_uint8(image_path)
    meta: Dict[str, Any] = {
        "cropped": False,
        "face_confidence": None,
        "detector_bbox": None,
        "crop_bbox": None,
        "margin": None,
        "original_shape": list(rgb.shape),
    }
    face_rgb = rgb
    if crop_face:
        ok, reason = retinaface_available()
        if not ok:
            raise RuntimeError(reason)
        crop_info = crop_aligned_face(
            rgb,
            margin=face_margin,
            confidence_threshold=face_confidence,
        )
        face_rgb = crop_info["face_rgb"]
        meta.update(
            {
                "cropped": True,
                "face_confidence": crop_info["face_confidence"],
                "detector_bbox": crop_info["detector_bbox"],
                "crop_bbox": crop_info["crop_bbox"],
                "margin": crop_info["margin"],
            }
        )

    batch = preprocess_rgb_to_tensor(face_rgb)
    return {"tensor": batch, "face_rgb": face_rgb, "meta": meta}


def preprocess_image(
    image_path: str | Path,
    *,
    crop_face: bool = True,
    face_margin: float = _DEFAULT_FACE_MARGIN,
    face_confidence: float = _DEFAULT_FACE_CONF,
) -> torch.Tensor:
    """Load + optional face crop + albumentations 224 normalize."""
    prepared = prepare_face_input(
        image_path,
        crop_face=crop_face,
        face_margin=face_margin,
        face_confidence=face_confidence,
    )
    return prepared["tensor"]


def classify_probs(
    logits: torch.Tensor,
    *,
    threshold: float = 0.5,
) -> Tuple[str, float, float]:
    """Softmax; class index 1 = fake (official eval.py / dataset labels)."""
    probs = F.softmax(logits, dim=-1)
    real_prob = float(probs[0, 0].item())
    fake_prob = float(probs[0, 1].item())
    label = "fake" if fake_prob >= threshold else "real"
    return label, fake_prob, real_prob


def infer(
    image_path: str | Path,
    *,
    threshold: float = 0.5,
    prefer_cuda: bool = True,
    crop_face: bool = True,
    face_margin: float = _DEFAULT_FACE_MARGIN,
    face_confidence: float = _DEFAULT_FACE_CONF,
) -> Dict[str, Any]:
    """Run MoE-FFD on a single image path (RetinaFace crop by default)."""
    checkpoint = moe_ffd_checkpoint_path()
    device = resolve_inference_device(prefer_cuda=prefer_cuda)
    model = _load_model(device, checkpoint)

    prepared = prepare_face_input(
        image_path,
        crop_face=crop_face,
        face_margin=face_margin,
        face_confidence=face_confidence,
    )
    batch = prepared["tensor"].to(device)
    with torch.no_grad():
        outputs = model(batch)
        logits = outputs[0] if isinstance(outputs, (tuple, list)) else outputs

    label, fake_prob, real_prob = classify_probs(logits, threshold=threshold)
    preprocess_tag = (
        "retinaface_crop+albumentations_official_v1"
        if prepared["meta"]["cropped"]
        else "albumentations_official_v1_no_crop"
    )
    return {
        "label": label,
        "fake_prob": fake_prob,
        "real_prob": real_prob,
        "score": fake_prob,
        "threshold": float(threshold),
        "inference_device": str(device),
        "model_checkpoint": checkpoint.name,
        "checkpoint_epoch": _cached.get("epoch"),
        "preprocess": preprocess_tag,
        "class_mapping": {"0": "real", "1": "fake"},
        "face_cropped": prepared["meta"]["cropped"],
        "face_confidence": prepared["meta"]["face_confidence"],
        "face_margin": prepared["meta"]["margin"],
        "detector_bbox": prepared["meta"]["detector_bbox"],
        "crop_bbox": prepared["meta"]["crop_bbox"],
        "original_shape": prepared["meta"]["original_shape"],
        "face_rgb": prepared["face_rgb"],
        "input_tensor_shape": list(batch.shape),
        "input_tensor_mean": float(batch.mean().item()),
        "logits": [float(x) for x in logits.detach().cpu().reshape(-1).tolist()],
    }


def clear_model_cache() -> None:
    with _model_lock:
        _cached["model"] = None
        _cached["device"] = None
        _cached["checkpoint"] = None
        _cached["epoch"] = None
