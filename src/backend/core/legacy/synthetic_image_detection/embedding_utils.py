"""Helpers to capture penultimate-layer embeddings from synthetic-image detectors.

The hooks register on the input of the final classification layer, so the
forward pass (and therefore the reported score) is unchanged.  Embeddings are
returned as ``np.ndarray`` of dtype ``float32``.
"""

from __future__ import annotations

from typing import Any, Callable

import numpy as np
import torch
from PIL import Image


def _capture_fc_input(module: Any, inputs: tuple[Any, ...], store: list[torch.Tensor]) -> None:
    """Hook that stores the tensor entering a fully-connected/classifier layer."""
    if inputs and inputs[0] is not None:
        store.append(inputs[0].detach().cpu())


def flatten_embedding(t: torch.Tensor) -> np.ndarray:
    """Convert a stored activation to a 1-D float32 numpy array."""
    return t.detach().cpu().reshape(-1).numpy().astype(np.float32)


def _flatten_embedding(t: torch.Tensor) -> np.ndarray:
    return flatten_embedding(t)


def register_fc_input_hook(module: torch.nn.Module) -> tuple[Any, list[torch.Tensor]]:
    """Register a forward hook on ``module`` that captures its input activations.

    Returns the hook handle and a list that is appended to during every forward.
    """
    store: list[torch.Tensor] = []

    def _hook(_module: Any, inputs: tuple[Any, ...], _output: Any) -> None:
        _capture_fc_input(_module, inputs, store)

    handle = module.register_forward_hook(_hook)
    return handle, store


def extract_safe_embedding(image: Image.Image, device: torch.device | None = None) -> np.ndarray:
    """Extract SAFE embedding from the input of ``fc1`` (after avgpool)."""
    from core.legacy.safe.safe_pipeline import infer_safe_from_pil

    _, emb = infer_safe_from_pil(image, device or torch.device("cpu"), return_embedding=True)
    return emb


def extract_sdxl_flux_embedding(image: Image.Image, model: Any, feature_extractor: Any) -> np.ndarray:
    """Extract embedding from ``cmckinle/sdxl-flux-detector_v1.1`` (Swin-B).

    ``model`` is an ``AutoModelForImageClassification`` instance already on the
    target device.  The pooler output has shape ``(1, 1024)``.
    """
    rgb = image.convert("RGB")
    inputs = feature_extractor(rgb, return_tensors="pt").to(model.device)

    with torch.no_grad():
        outputs = model.swin(**inputs)
        emb = outputs.pooler_output.squeeze(-1)  # (1, 1024)

    return _flatten_embedding(emb)


def extract_ai_image_detector_embedding(
    image: Image.Image,
    model: Any,
    image_processor: Any,
) -> np.ndarray:
    """Extract embedding from ``haywoodsloan/ai-image-detector-deploy`` (Swinv2-L).

    The legacy pipeline loads this model via ``pipeline()``.  For embedding
    extraction we call the underlying ``AutoModelForImageClassification``
    directly; the logits are identical because the classifier is still applied
    to the same pooler output.
    """
    rgb = image.convert("RGB")
    inputs = image_processor(rgb, return_tensors="pt").to(model.device)

    with torch.no_grad():
        outputs = model.swinv2(**inputs)
        emb = outputs.pooler_output.squeeze(-1)  # (1, 1536)

    return _flatten_embedding(emb)


def extract_bfree_embedding(image: Image.Image, device: torch.device | None = None) -> np.ndarray:
    """Extract B-Free embedding from the input of the timm head."""
    from core.legacy.bfree.bfree_pipeline import infer_bfree_from_pil

    _, emb = infer_bfree_from_pil(image, device or torch.device("cpu"), return_embedding=True)
    return emb


def extract_clipd_embedding(image: Image.Image, device: torch.device | None = None) -> np.ndarray:
    """Extract GRIP CLIP-D (clipdet_latent10k_plus) embedding from ``model.fc`` input."""
    from core.legacy.truebees_clip_d.clipd_pipeline import MODEL_NAME, infer_clipd_from_pil

    _, emb = infer_clipd_from_pil(image, device or torch.device("cpu"), return_embedding=True, model_name=MODEL_NAME)
    return emb


def extract_corvi2023_embedding(
    image: Image.Image,
    device: torch.device | None = None,
    tile_size: int = 1024,
) -> np.ndarray:
    """Extract Corvi2023 embedding averaging tile embeddings."""
    from core.legacy.truebees_clip_d.clipd_pipeline import infer_corvi2023_from_pil

    *_, emb = infer_corvi2023_from_pil(
        image,
        device or torch.device("cpu"),
        tile_size,
        return_embedding=True,
    )
    return emb


# Generic dispatcher used by the extraction script and the adapter.
EMBEDDING_EXTRACTORS: dict[str, Callable[..., np.ndarray]] = {
    "safe": extract_safe_embedding,
    "sdxl_flux_detector_v1_1": extract_sdxl_flux_embedding,
    "ai_image_detector_deploy": extract_ai_image_detector_embedding,
    "bfree": extract_bfree_embedding,
    "corvi2023": extract_corvi2023_embedding,
    "clipd": extract_clipd_embedding,
}


def extract_detector_embedding(
    detector_id: str,
    image: Image.Image,
    *,
    device: torch.device | None = None,
    model: Any | None = None,
    feature_extractor: Any | None = None,
    image_processor: Any | None = None,
) -> np.ndarray:
    """Extract embedding for ``detector_id`` from ``image``.

    For HuggingFace detectors the caller must provide the loaded ``model`` and
    processor/feature extractor.  For legacy detectors (SAFE, B-Free, CLIP-D,
    Corvi2023) only ``device`` is required because they manage their own cache.
    """
    if detector_id == "safe":
        return extract_safe_embedding(image, device=device)
    if detector_id == "sdxl_flux_detector_v1_1":
        if model is None or feature_extractor is None:
            raise ValueError("sdxl_flux_detector_v1_1 embedding requires model and feature_extractor")
        return extract_sdxl_flux_embedding(image, model, feature_extractor)
    if detector_id == "ai_image_detector_deploy":
        if model is None or image_processor is None:
            raise ValueError("ai_image_detector_deploy embedding requires model and image_processor")
        return extract_ai_image_detector_embedding(image, model, image_processor)
    if detector_id == "bfree":
        return extract_bfree_embedding(image, device=device)
    if detector_id == "corvi2023":
        return extract_corvi2023_embedding(image, device=device)
    if detector_id == "clipd":
        return extract_clipd_embedding(image, device=device)
    raise ValueError(f"No embedding extractor available for detector {detector_id}")
