"""Adapter — ClipBased-SyntheticImageDetection (GRIP-UNINA)."""

from __future__ import annotations

import gc
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

import pandas as pd
import torch
import yaml
from PIL import Image
from torchvision.transforms import CenterCrop, Compose, InterpolationMode, Resize

from core.forensic_plugin import ForensicPlugin
from core.gpu_inference import (
    device_display_label,
    prepare_vram_for_heavy_model,
    release_gpu_memory,
    resolve_inference_device,
)
from core.job_staging import job_artifact_dir
from core.progress import pop_progress_callback, report_progress

_CLIPBASED_VENDOR_DIR = Path(__file__).parent.parent.parent.parent.parent / "vendor" / "grip_clipbased_synthetic"
_CLIPBASED_WEIGHTS_DIR = _CLIPBASED_VENDOR_DIR / "weights"

import sys
if str(_CLIPBASED_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_CLIPBASED_VENDOR_DIR))

_model_cache: dict[str, Any] = {}


def _load_clipbased_stack(device, model_name: str):
    import importlib.util
    import sys

    cache_key = f"clipbased:{model_name}:{device}"
    if cache_key in _model_cache:
        return _model_cache[cache_key]

    vendor = str(_CLIPBASED_VENDOR_DIR)

    # Load vendor modules directly from file to avoid namespace conflicts.
    def load_module_from_file(module_name: str, rel_path: str):
        file_path = _CLIPBASED_VENDOR_DIR / rel_path
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load {file_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module

    # networks/__init__.py imports .openclipnet and .resnet_mod via relative imports.
    # We load the submodules first under a unique prefix, then patch them into the package.
    networks_pkg = importlib.util.module_from_spec(
        importlib.util.spec_from_loader("clipbased_networks", loader=None)
    )
    networks_pkg.__path__ = [str(_CLIPBASED_VENDOR_DIR / "networks")]
    sys.modules["clipbased_networks"] = networks_pkg

    openclipnet = load_module_from_file("clipbased_networks.openclipnet", "networks/openclipnet.py")
    resnet_mod = load_module_from_file("clipbased_networks.resnet_mod", "networks/resnet_mod.py")
    networks_init = load_module_from_file("clipbased_networks.__init__", "networks/__init__.py")

    create_architecture = networks_init.create_architecture
    load_weights = networks_init.load_weights

    processing = load_module_from_file("clipbased_processing", "utils/processing.py")
    make_normalize = processing.make_normalize

    config_path = _CLIPBASED_WEIGHTS_DIR / model_name / "config.yaml"
    with open(config_path) as fid:
        data = yaml.load(fid, Loader=yaml.FullLoader)
    model_path = _CLIPBASED_WEIGHTS_DIR / model_name / data["weights_file"]
    arch = data["arch"]
    norm_type = data["norm_type"]
    patch_size = data["patch_size"]

    model = load_weights(create_architecture(arch), str(model_path))
    model = model.to(device).eval()

    transform: list[Any] = []
    if patch_size is None:
        transform_key = f"none_{norm_type}"
    elif patch_size == "Clip224":
        transform.append(Resize(224, interpolation=InterpolationMode.BICUBIC))
        transform.append(CenterCrop((224, 224)))
        transform_key = f"Clip224_{norm_type}"
    elif isinstance(patch_size, (tuple, list)):
        transform.append(Resize(*patch_size))
        transform.append(CenterCrop(patch_size[0]))
        transform_key = f"res{patch_size[0]}_{norm_type}"
    elif patch_size > 0:
        transform.append(CenterCrop(patch_size))
        transform_key = f"crop{patch_size}_{norm_type}"
    else:
        transform_key = f"none_{norm_type}"

    transform.append(make_normalize(norm_type))
    transform = Compose(transform)

    stack = {
        "model": model,
        "transform": transform,
        "transform_key": transform_key,
        "model_name": model_name,
    }
    _model_cache[cache_key] = stack
    return stack


def clear_clipbased_model_cache() -> None:
    for key in list(_model_cache.keys()):
        stack = _model_cache.pop(key, None)
        if stack:
            release_gpu_memory(stack.get("model"))
    release_gpu_memory()
    gc.collect()


_AVAILABLE_MODELS = ["clipdet_latent10k_plus", "clipdet_latent10k", "Corvi2023"]


def clipbased_runtime_status() -> Tuple[bool, str]:
    if not _CLIPBASED_VENDOR_DIR.exists():
        return False, f"Vendor ClipBased nao encontrado em {_CLIPBASED_VENDOR_DIR}"
    if not _CLIPBASED_WEIGHTS_DIR.exists():
        return False, f"Pesos ClipBased nao encontrados em {_CLIPBASED_WEIGHTS_DIR}"
    for model_name in _AVAILABLE_MODELS:
        config = _CLIPBASED_WEIGHTS_DIR / model_name / "config.yaml"
        weights = _CLIPBASED_WEIGHTS_DIR / model_name / "weights.pth"
        if config.exists() and weights.exists():
            return True, ""
    return False, "Nenhum modelo ClipBased com pesos disponivel"


def _sigmoid(x: float) -> float:
    import math
    return 1.0 / (1.0 + math.exp(-x))


def _resize_for_clipbased(image: Image.Image, max_size: int) -> Image.Image:
    """Resize preserving aspect ratio so the largest side <= max_size."""
    width, height = image.size
    if max(width, height) <= max_size:
        return image
    if width >= height:
        new_width = max_size
        new_height = int(round(height * max_size / width))
    else:
        new_height = max_size
        new_width = int(round(width * max_size / height))
    return image.resize((new_width, new_height), Image.Resampling.LANCZOS)


def _extract_tiles(image: Image.Image, tile_size: int):
    """Split image into non-overlapping square tiles of at most tile_size."""
    width, height = image.size
    if width <= tile_size and height <= tile_size:
        return [image]
    tiles = []
    for y in range(0, height, tile_size):
        for x in range(0, width, tile_size):
            box = (x, y, min(x + tile_size, width), min(y + tile_size, height))
            tiles.append(image.crop(box))
    return tiles


def _run_clipbased_inference(model, transform, image: Image.Image, device, tile_size: int):
    """Run inference. If image is larger than tile_size, use tile-based inference."""
    original_size = image.size
    width, height = original_size
    if width <= tile_size and height <= tile_size:
        img_t = transform(image).unsqueeze(0).to(device)
        with torch.no_grad():
            out_tens = model(img_t).cpu().numpy()
        return out_tens, 1, original_size, False

    tiles = _extract_tiles(image, tile_size)
    logits = []
    for tile in tiles:
        img_t = transform(tile).unsqueeze(0).to(device)
        with torch.no_grad():
            out_tens = model(img_t).cpu().numpy()

        if out_tens.shape[1] == 1:
            out_tens = out_tens[:, 0]
        elif out_tens.shape[1] == 2:
            out_tens = out_tens[:, 1] - out_tens[:, 0]

        if len(out_tens.shape) > 1:
            logit = float(out_tens.mean((1, 2))[0])
        else:
            logit = float(out_tens[0])
        logits.append(logit)

    # Aggregate tile logits by simple mean.
    mean_logit = float(sum(logits) / len(logits)) if logits else 0.0
    # Build a pseudo tensor shape so downstream code can also fall back to scalar logic.
    out_tens = torch.tensor([[mean_logit]]).numpy()
    return out_tens, len(tiles), original_size, True


class ClipBasedSyntheticAdapter(ForensicPlugin):
    """ClipBased-SyntheticImageDetection — detector universal baseado em CLIP."""

    @property
    def name(self) -> str:
        return "clipbased_synthetic"

    @property
    def supported_types(self) -> list[str]:
        return ["imagem"]

    @classmethod
    def is_runtime_available(cls) -> Tuple[bool, str]:
        return clipbased_runtime_status()

    def validate_parameters(self, parameters: Dict[str, Any]) -> Tuple[bool, str]:
        ok, reason = clipbased_runtime_status()
        if not ok:
            return False, reason
        model_name = parameters.get("model_name", "clipdet_latent10k_plus")
        if model_name not in _AVAILABLE_MODELS:
            return False, f"model_name deve ser um de: {', '.join(_AVAILABLE_MODELS)}"
        keep_loaded = parameters.get("keep_model_loaded")
        if keep_loaded is not None and not isinstance(keep_loaded, bool):
            return False, "keep_model_loaded deve ser booleano"
        max_input_size = parameters.get("max_input_size", 1024)
        if not isinstance(max_input_size, int) or max_input_size < 64 or max_input_size > 4096:
            return False, "max_input_size deve ser inteiro entre 64 e 4096"
        return True, ""

    def analyze(self, evidence_path: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        on_progress = pop_progress_callback(parameters)
        ok, reason = clipbased_runtime_status()
        if not ok:
            return {"success": False, "error": reason, "adapter": "clipbased_synthetic", "status": "unavailable"}

        keep_loaded = bool(parameters.get("keep_model_loaded", False))

        try:
            report_progress(on_progress, 5, "Carregando ClipBased")
            prepare_vram_for_heavy_model()
            device = resolve_inference_device()
            model_name = str(parameters.get("model_name", "clipdet_latent10k_plus"))
            stack = _load_clipbased_stack(device, model_name)
            model = stack["model"]
            transform = stack["transform"]

            report_progress(on_progress, 35, "Preparando imagem")
            tile_size = int(parameters.get("max_input_size", 1024))
            image = Image.open(evidence_path).convert("RGB")

            report_progress(on_progress, 60, "Executando inferencia CLIP")
            out_tens, num_tiles, original_size, tiled = _run_clipbased_inference(
                model, transform, image, device, tile_size
            )

            if out_tens.shape[1] == 1:
                out_tens = out_tens[:, 0]
            elif out_tens.shape[1] == 2:
                out_tens = out_tens[:, 1] - out_tens[:, 0]

            if len(out_tens.shape) > 1:
                logit = float(out_tens.mean((1, 2))[0])
            else:
                logit = float(out_tens[0])

            # LLR > 0 => synthetic (README). Convert to calibrated fake probability.
            fake_score = _sigmoid(logit)
            real_score = 1.0 - fake_score
            prediction = "FAKE" if logit > 0 else "REAL"

            report_progress(on_progress, 90, "Salvando relatorio")
            out_dir = job_artifact_dir(parameters, fallback_subdir="clipbased_synthetic_tmp")
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

            tile_note = f" (dividida em {num_tiles} tile(s); original {original_size[0]}x{original_size[1]})" if tiled else ""
            processed_size = image.size if not tiled else (tile_size, tile_size)
            report_path = out_dir / f"clipbased_report_{stamp}.txt"
            report_path.write_text(
                f"Modelo: {model_name}\n"
                f"Tamanho de entrada: {processed_size[0]}x{processed_size[1]}{tile_note}\n"
                f"tile_size: {tile_size}\n"
                f"num_tiles: {num_tiles}\n"
                f"LLR (logit): {logit:.6f}\n"
                f"Classificacao: {prediction}\n"
                f"Score AI (fake): {fake_score:.4f}\n"
                f"Score Real: {real_score:.4f}\n"
                f"Dispositivo: {device_display_label(device)}\n",
                encoding="utf-8",
            )

            json_path = out_dir / "clipbased_report.json"
            json_path.write_text(
                __import__("json").dumps(
                    {
                        "model_name": model_name,
                        "input_width": processed_size[0],
                        "input_height": processed_size[1],
                        "original_width": original_size[0],
                        "original_height": original_size[1],
                        "tiled": tiled,
                        "num_tiles": num_tiles,
                        "tile_size": tile_size,
                        "llr": logit,
                        "prediction": prediction,
                        "fake_score": fake_score,
                        "real_score": real_score,
                        "inference_device": device_display_label(device),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            result: Dict[str, Any] = {
                "success": True,
                "adapter": "clipbased_synthetic",
                "status": "completed",
                "model_name": model_name,
                "llr": logit,
                "prediction": prediction,
                "fake_score": fake_score,
                "real_score": real_score,
                "inference_device": device_display_label(device),
                "report_path": str(report_path),
                "clipbased_report_json_path": str(json_path),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            report_progress(on_progress, 100, "Concluido")
            return result

        except Exception as exc:
            return {"success": False, "error": str(exc), "adapter": "clipbased_synthetic"}

        finally:
            if not keep_loaded:
                clear_clipbased_model_cache()
