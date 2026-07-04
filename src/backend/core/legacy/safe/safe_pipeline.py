"""SAFE (KDD'25) — single-image synthetic detection inference."""

from __future__ import annotations

import importlib.util
import logging
import math
from typing import Callable

import torch
import torch.nn.functional as F
import numpy as np
from PIL import Image
from torchvision import transforms
from torchvision.transforms import InterpolationMode

from core.gpu_inference import (
    device_display_label,
    release_gpu_memory,
    resolve_inference_device,
    run_with_device_fallback,
)
from core.legacy.effort.effort_pipeline import effort_row
from core.legacy.safe.safe_runtime import resolve_checkpoint, safe_runtime_status, safe_vendor_dir

logger = logging.getLogger(__name__)

ProgressFn = Callable[[int, str], None] | None

INPUT_SIZE = 256
MODEL_LABEL = "SAFE (KDD'25)"

_model_cache: dict[str, torch.nn.Module] = {}


def _report(on_progress: ProgressFn, pct: int, label: str) -> None:
    if on_progress:
        on_progress(pct, label)


def _load_safe_resnet50():
    """Carrega resnet50 do vendor sem colidir com o pacote backend `models`."""
    module_path = safe_vendor_dir() / "models" / "resnet.py"
    if not module_path.is_file():
        raise RuntimeError(f"SAFE resnet.py ausente em {module_path}")
    spec = importlib.util.spec_from_file_location("safe_vendor_resnet", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Nao foi possivel carregar {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    factory = getattr(module, "resnet50", None)
    if factory is None:
        raise RuntimeError("SAFE resnet50 nao encontrado no vendor")
    return factory


class _SafeEvalTransform:
    """CenterCrop 256x256 — transformação de eval oficial do SAFE.

    O checkpoint SAFE é treinado/avaliado com ``--transform_mode crop``
    (``CenterCrop([256, 256])`` + ``ToTensor()``). Para imagens forenses
    menores que 256 px em algum eixo, fazemos um resize curto para 256 px
    antes do crop, mantendo o método o mais fiel possível ao paper.
    """

    def __call__(self, image: Image.Image) -> torch.Tensor:
        w, h = image.size
        if h < INPUT_SIZE or w < INPUT_SIZE:
            image = transforms.Resize(
                INPUT_SIZE,
                interpolation=InterpolationMode.BILINEAR,
            )(image)
        image = transforms.CenterCrop((INPUT_SIZE, INPUT_SIZE))(image)
        return transforms.ToTensor()(image)


def _eval_transform() -> _SafeEvalTransform:
    return _SafeEvalTransform()


def _load_model(device: torch.device) -> torch.nn.Module:
    cache_key = device.type
    if cache_key in _model_cache:
        return _model_cache[cache_key]

    ckpt_path = resolve_checkpoint()
    if ckpt_path is None:
        raise RuntimeError("Checkpoint SAFE ausente")

    resnet50 = _load_safe_resnet50()
    model = resnet50(num_classes=2)
    try:
        obj = torch.load(str(ckpt_path), map_location="cpu", weights_only=False)
    except TypeError:
        obj = torch.load(str(ckpt_path), map_location="cpu")

    state = obj.get("model", obj) if isinstance(obj, dict) else obj
    if isinstance(state, dict):
        state = {k.replace("module.", ""): v for k, v in state.items()}
    model.load_state_dict(state, strict=True)
    model = model.to(device)
    model.eval()
    _model_cache[cache_key] = model
    return model


def clear_safe_model_cache() -> None:
    for model in list(_model_cache.values()):
        release_gpu_memory(model)
    _model_cache.clear()
    release_gpu_memory()


def safe_model_cache_keys() -> list[str]:
    return list(_model_cache.keys())


def infer_safe_from_pil(image: Image.Image, device: torch.device) -> float:
    """Retorna probabilidade de imagem sintetica (classe fake=1)."""
    model = _load_model(device)
    tensor = _eval_transform()(image.convert("RGB")).unsqueeze(0).to(device)
    with torch.no_grad():
        logits = model(tensor)
        prob_fake = F.softmax(logits, dim=1)[0, 1].item()
    return float(prob_fake)


def _prob_to_logit(prob: float, eps: float = 1e-8) -> float:
    """Convert probability to logit."""
    p = min(max(float(prob), eps), 1.0 - eps)
    return math.log(p / (1.0 - p))


def _logit_to_prob(logit: float) -> float:
    """Convert logit to probability via sigmoid."""
    return 1.0 / (1.0 + math.exp(-float(logit)))


def _extract_safe_tiles(image: Image.Image, n_tiles: int = 4) -> list[Image.Image]:
    """Extract N 256x256 tiles for SAFE inference.

    Tile 0 is always the central crop (original SAFE eval). Additional tiles are
    taken from distinct quadrants to cover different image regions.

    If the image is smaller than 256x256 in any dimension, resize the short side
    to 256 before cropping, matching the original SAFE fallback behaviour.
    """
    rgb = image.convert("RGB")
    w, h = rgb.size

    # Match SAFE fallback for small images.
    if h < INPUT_SIZE or w < INPUT_SIZE:
        rgb = transforms.Resize(INPUT_SIZE, interpolation=InterpolationMode.BILINEAR)(rgb)
        w, h = rgb.size

    tiles: list[Image.Image] = []

    # Tile 0: central crop (original SAFE evaluation).
    left = (w - INPUT_SIZE) // 2
    top = (h - INPUT_SIZE) // 2
    tiles.append(rgb.crop((left, top, left + INPUT_SIZE, top + INPUT_SIZE)))

    if n_tiles <= 1 or w < INPUT_SIZE or h < INPUT_SIZE:
        return tiles

    # Quadrant anchors for additional tiles.
    quadrants = [
        (0, 0),                      # top-left
        (w - INPUT_SIZE, 0),         # top-right
        (0, h - INPUT_SIZE),         # bottom-left
        (w - INPUT_SIZE, h - INPUT_SIZE),  # bottom-right
    ]

    # Skip central quadrant (would overlap tile 0 significantly).
    used_quadrants = 0
    for (left, top) in quadrants:
        if used_quadrants >= n_tiles - 1:
            break
        # Avoid crops that are essentially the center tile.
        center_left = (w - INPUT_SIZE) // 2
        center_top = (h - INPUT_SIZE) // 2
        if abs(left - center_left) < INPUT_SIZE // 4 and abs(top - center_top) < INPUT_SIZE // 4:
            continue
        tiles.append(rgb.crop((left, top, left + INPUT_SIZE, top + INPUT_SIZE)))
        used_quadrants += 1

    # If we still need more tiles and image is large enough, add mid-side crops.
    while len(tiles) < n_tiles and (w >= INPUT_SIZE * 2 or h >= INPUT_SIZE * 2):
        idx = len(tiles) - 1
        if idx == 1 and w >= INPUT_SIZE * 2:
            left = (w // 2) - (INPUT_SIZE // 2)
            top = 0
        elif idx == 2 and h >= INPUT_SIZE * 2:
            left = 0
            top = (h // 2) - (INPUT_SIZE // 2)
        elif idx == 3 and w >= INPUT_SIZE * 2 and h >= INPUT_SIZE * 2:
            left = (w // 2) - (INPUT_SIZE // 2)
            top = (h // 2) - (INPUT_SIZE // 2)
        else:
            break
        tiles.append(rgb.crop((left, top, left + INPUT_SIZE, top + INPUT_SIZE)))

    return tiles[:n_tiles]


def infer_safe_from_pil_tiled(
    image: Image.Image,
    device: torch.device,
    n_tiles: int = 4,
) -> float:
    """Run SAFE on N tiles and return aggregated fake probability.

    Tile 0 is always the central 256x256 crop. Remaining tiles are extracted
    from distinct image regions. Probabilities are converted to logits, averaged,
    and mapped back through sigmoid. This preserves the calibration shape better
    than averaging probabilities directly.
    """
    model = _load_model(device)
    tiles = _extract_safe_tiles(image, n_tiles=n_tiles)

    logits: list[float] = []
    for tile in tiles:
        tensor = transforms.ToTensor()(tile).unsqueeze(0).to(device)
        with torch.no_grad():
            output = model(tensor)
            prob_fake = F.softmax(output, dim=1)[0, 1].item()
        logits.append(_prob_to_logit(prob_fake))

    mean_logit = float(np.mean(logits))
    return _logit_to_prob(mean_logit)


def predict_safe_row(
    image: Image.Image,
    on_progress: ProgressFn = None,
) -> list[str] | None:
    """Uma linha SAFE para a tabela de detecção de imagens sinteticas."""
    ok, reason = safe_runtime_status()
    if not ok:
        logger.debug("SAFE indisponivel: %s", reason)
        return None

    preferred = resolve_inference_device()
    pct = 62
    _report(on_progress, pct, f"Inferindo {MODEL_LABEL} em {device_display_label(preferred)}…")

    def _run(dev: torch.device):
        return infer_safe_from_pil(image, dev)

    def _on_cpu_fallback(exc_reason: str) -> None:
        _report(on_progress, pct, f"{MODEL_LABEL} em CPU — fallback VRAM…")

    try:
        prob, device = run_with_device_fallback(
            _run,
            on_fallback=clear_safe_model_cache,
            on_before_cpu_fallback=_on_cpu_fallback,
        )
    except Exception as exc:
        logger.warning("SAFE falhou: %s", exc)
        return None

    return effort_row(MODEL_LABEL, prob, inference_device=device.type)


def warm_safe_model(*, device: torch.device | None = None) -> bool:
    """Pre-carrega SAFE e executa forward dummy (mantem em cache)."""
    ok, _ = safe_runtime_status()
    if not ok:
        return False
    target = device or resolve_inference_device()
    model = _load_model(target)
    dummy = torch.zeros(1, 3, INPUT_SIZE, INPUT_SIZE, device=target)
    with torch.no_grad():
        model(dummy)
    return True
