"""Noiseprint inference pipeline — extraction (PyTorch) + blind localization (GRIP-UNINA)."""

from __future__ import annotations

import gc
import os
import sys
import types
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image

from core.gpu_inference import release_gpu_memory, run_with_device_fallback
from core.legacy.noiseprint.grip_blind import (
    heatmap_jet_image,
    noiseprint_blind_post,
    overlay_heatmap_jet,
    overlay_valid_mask,
    valid_mask_image,
)
from core.legacy.noiseprint.noiseprint_runtime import (
    noiseprint_repo_dir,
    resolve_noiseprint_weights_dir,
)

ProgressFn = Callable[[int, str], None] | None

_NOISEPRINT_NET_CACHE: dict[str, object] = {}


def _noiseprint_cache_key(qf: int, device) -> str:
    dev = device.type if hasattr(device, "type") else str(device)
    return f"qf{int(qf)}:{dev}"


def _load_noiseprint_net(qf: int, device, weight_path: Path):
    import torch

    from Noiseprint import FullConvNet

    key = _noiseprint_cache_key(qf, device)
    cached = _NOISEPRINT_NET_CACHE.get(key)
    if cached is not None:
        from core.gpu_residency import touch_lru

        touch_lru("noiseprint")
        return cached

    net = FullConvNet(0.9, torch.tensor(False), num_levels=17)
    try:
        state = torch.load(str(weight_path), map_location=device, weights_only=False)
    except TypeError:
        state = torch.load(str(weight_path), map_location=device)
    net.load_state_dict(state)
    _bind_noiseprint_inference_forward(net)
    net.to(device)
    net.eval()
    _NOISEPRINT_NET_CACHE[key] = net
    from core.gpu_residency import touch_lru

    touch_lru("noiseprint")
    return net


def clear_noiseprint_net_cache() -> None:
    for net in list(_NOISEPRINT_NET_CACHE.values()):
        _release_noiseprint_net(net)
    _NOISEPRINT_NET_CACHE.clear()
    release_gpu_memory()

BORDER_TRIM = 34


@dataclass
class NoiseprintAnalysisResult:
    input_image: Image.Image
    heatmap_image: Image.Image
    overlay_image: Image.Image
    noiseprint_image: Image.Image
    valid_mask_image: Image.Image
    valid_overlay_image: Image.Image
    original_size: tuple[int, int]
    jpeg_quality_factor: int
    mean_noiseprint: float
    valid_pixel_fraction: float
    inference_device: str
    blind_status: str


def _patch_pillow_jpeg_qtables() -> None:
    """Noiseprint legado importa convert_dict_qtables (removido no Pillow 10+)."""
    import PIL.JpegImagePlugin as jpeg_plugin

    if hasattr(jpeg_plugin, "convert_dict_qtables"):
        return

    def convert_dict_qtables(qtables):
        return qtables

    jpeg_plugin.convert_dict_qtables = convert_dict_qtables


def _ensure_noiseprint_import_path() -> None:
    _patch_pillow_jpeg_qtables()
    root = str(noiseprint_repo_dir())
    if root not in sys.path:
        sys.path.insert(0, root)


def _report(on_progress: ProgressFn, pct: int, label: str) -> None:
    if on_progress:
        on_progress(pct, label)


@contextmanager
def _noiseprint_workdir():
    """Run vendor code with expected relative weight paths."""
    repo = noiseprint_repo_dir()
    weights = resolve_noiseprint_weights_dir()
    if weights is None:
        raise RuntimeError("Pesos Noiseprint nao encontrados")

    vendor_weights = repo / "pretrained_weights"
    created_symlink = False
    if not vendor_weights.is_dir() or not (vendor_weights / "model_qf101.pth").is_file():
        vendor_weights.parent.mkdir(parents=True, exist_ok=True)
        if vendor_weights.exists() or vendor_weights.is_symlink():
            if vendor_weights.is_symlink():
                vendor_weights.unlink()
            elif vendor_weights.is_dir() and not any(vendor_weights.iterdir()):
                vendor_weights.rmdir()
        try:
            os.symlink(weights, vendor_weights)
            created_symlink = True
        except OSError:
            import shutil

            if vendor_weights.exists():
                shutil.rmtree(vendor_weights)
            shutil.copytree(weights, vendor_weights)

    prev = os.getcwd()
    os.chdir(repo)
    try:
        yield
    finally:
        os.chdir(prev)
        if created_symlink and vendor_weights.is_symlink():
            vendor_weights.unlink()


def _normalize_extraction_map(res: np.ndarray) -> tuple[np.ndarray, float, float]:
    """Grayscale normalization for raw noiseprint map display (vendor showout style)."""
    h, w = res.shape[:2]
    b = BORDER_TRIM
    if h > 2 * b and w > 2 * b:
        core = res[b:-b, b:-b]
    else:
        core = res
    vmin = float(np.min(core))
    vmax = float(np.max(core))
    span = max(vmax - vmin, 1e-8)
    norm = np.clip((res - vmin) / span, 0.0, 1.0)
    return norm.astype(np.float32), vmin, vmax


def _array_to_pil_gray(arr: np.ndarray) -> Image.Image:
    channel = np.clip(arr * 255.0, 0, 255).astype(np.uint8)
    return Image.fromarray(channel, mode="L")


def _inference_forward(self, x):
    """Same math as vendor FullConvNet.forward without caching all layer maps on GPU."""
    for layer in self.conv_layers:
        x = layer(x)
    return x


def _bind_noiseprint_inference_forward(net) -> None:
    net.forward = types.MethodType(_inference_forward, net)


def _clear_noiseprint_level_cache(net) -> None:
    levels = getattr(net, "level", None)
    if not levels:
        return
    for idx, tensor in enumerate(levels):
        if tensor is not None:
            levels[idx] = None


def _release_noiseprint_net(net) -> None:
    _clear_noiseprint_level_cache(net)
    release_gpu_memory(net)


def _resolve_weight_path(qf: int) -> Path:
    weights = resolve_noiseprint_weights_dir()
    if weights is None:
        raise RuntimeError("Pesos Noiseprint nao encontrados")
    preferred = weights / f"model_qf{int(qf)}.pth"
    if preferred.is_file():
        return preferred
    fallback = weights / "model_qf101.pth"
    if fallback.is_file():
        return fallback
    raise RuntimeError(f"Peso Noiseprint ausente para QF {qf}")


def _load_gray_image(evidence_path: str) -> np.ndarray:
    _ensure_noiseprint_import_path()
    from utilityRead import imread2f

    img, _mode = imread2f(evidence_path, channel=1)
    return img


def _load_rgb_image(evidence_path: str) -> tuple[np.ndarray, tuple[int, int]]:
    _ensure_noiseprint_import_path()
    from utilityRead import imread2f

    img, _mode = imread2f(evidence_path, channel=3)
    return img, (img.shape[0], img.shape[1])


def _extract_noiseprint_map(
    evidence_path: str,
    device,
    qf: int,
    *,
    img_gray: np.ndarray | None = None,
) -> np.ndarray:
    """Device-aware Noiseprint extraction (PyTorch port of GRIP-UNINA)."""
    import torch
    import torchvision.transforms as transforms

    _ensure_noiseprint_import_path()
    from Noiseprint import FullConvNet

    img = img_gray if img_gray is not None else _load_gray_image(evidence_path)
    slide = 1024
    large_limit = 1_050_000
    overlap = 34
    transform = transforms.ToTensor()
    weight_path = _resolve_weight_path(qf)

    net = _load_noiseprint_net(qf, device, weight_path)
    cache_key = _noiseprint_cache_key(qf, device)

    try:
        with torch.no_grad():
            if img.shape[0] * img.shape[1] > large_limit:
                res = np.zeros((img.shape[0], img.shape[1]), np.float32)
                for index0 in range(0, img.shape[0], slide):
                    index0start = index0 - overlap
                    index0end = index0 + slide + overlap
                    for index1 in range(0, img.shape[1], slide):
                        index1start = index1 - overlap
                        index1end = index1 + slide + overlap
                        clip = img[
                            max(index0start, 0) : min(index0end, img.shape[0]),
                            max(index1start, 0) : min(index1end, img.shape[1]),
                        ]
                        tensor_image = transform(clip).to(device)
                        tensor_image = tensor_image.reshape(
                            1, 1, tensor_image.shape[1], tensor_image.shape[2]
                        )
                        res_b = net(tensor_image)[0][0]
                        if index0 > 0:
                            res_b = res_b[overlap:, :]
                        if index1 > 0:
                            res_b = res_b[:, overlap:]
                        res_b = res_b[: min(slide, res_b.shape[0]), : min(slide, res_b.shape[1])]
                        res[
                            index0 : min(index0 + slide, res.shape[0]),
                            index1 : min(index1 + slide, res.shape[1]),
                        ] = res_b.detach().cpu().numpy()
            else:
                tensor_image = transform(img).to(device)
                tensor_image = tensor_image.reshape(
                    1, 1, tensor_image.shape[1], tensor_image.shape[2]
                )
                res = net(tensor_image)[0][0].detach().cpu().numpy()
    finally:
        _clear_noiseprint_level_cache(net)
        from core.gpu_residency import lru_expired, should_keep_resident

        if not should_keep_resident("noiseprint") or lru_expired("noiseprint"):
            _release_noiseprint_net(net)
            _NOISEPRINT_NET_CACHE.pop(cache_key, None)
        gc.collect()

    return res


def _detect_jpeg_qf(evidence_path: str) -> int:
    _ensure_noiseprint_import_path()
    from utilityRead import jpeg_qtableinv

    try:
        return int(jpeg_qtableinv(evidence_path))
    except Exception:
        return 101


def _run_noiseprint_on_device(
    evidence_path: str,
    *,
    on_progress: ProgressFn,
    device,
) -> NoiseprintAnalysisResult:
    _report(on_progress, 5, "Carregando evidencia")
    img_gray = _load_gray_image(evidence_path)
    img_rgb, original_size = _load_rgb_image(evidence_path)
    qf = _detect_jpeg_qf(evidence_path)
    _report(on_progress, 10, f"QF JPEG detectado: {qf}")

    label = "GPU" if device.type == "cuda" else "CPU (lento — pode levar minutos)"
    _report(on_progress, 20, f"Extraindo Noiseprint em {label}")
    with _noiseprint_workdir():
        res = _extract_noiseprint_map(evidence_path, device, qf, img_gray=img_gray)

    if res.shape[:2] != original_size:
        raise RuntimeError(
            f"Mapa Noiseprint {res.shape[:2]} difere da imagem {original_size}"
        )

    _report(on_progress, 70, "Localizacao blind (GRIP-UNINA)")
    blind = noiseprint_blind_post(res, img_gray)
    if blind.status != "ok" or blind.mapp_float is None:
        raise RuntimeError(
            "Imagem muito pequena ou uniforme para localizacao blind Noiseprint"
        )

    _report(on_progress, 85, "Gerando heatmap de falsificacao")
    extraction_norm, vmin, vmax = _normalize_extraction_map(res)
    mean_val = float(np.mean(extraction_norm))

    input_image = Image.fromarray((np.clip(img_rgb, 0, 1) * 255).astype(np.uint8), mode="RGB")
    heatmap_img = heatmap_jet_image(blind.mapp_float, blind.valid_mask_full)
    overlay_img = overlay_heatmap_jet(
        (np.clip(img_rgb, 0, 1) * 255).astype(np.uint8),
        blind.mapp_float,
        blind.valid_mask_full,
    )
    noiseprint_img = _array_to_pil_gray(extraction_norm)
    valid_mask = valid_mask_image(blind.valid_mask_full)
    valid_overlay = overlay_valid_mask(
        (np.clip(img_rgb, 0, 1) * 255).astype(np.uint8),
        blind.valid_mask_full,
    )
    _report(on_progress, 95, "Noiseprint concluido")

    return NoiseprintAnalysisResult(
        input_image=input_image,
        heatmap_image=heatmap_img,
        overlay_image=overlay_img,
        noiseprint_image=noiseprint_img,
        valid_mask_image=valid_mask,
        valid_overlay_image=valid_overlay,
        original_size=original_size,
        jpeg_quality_factor=qf,
        mean_noiseprint=mean_val,
        valid_pixel_fraction=float(blind.valid_pixel_fraction or 0.0),
        inference_device=device.type,
        blind_status=blind.status,
    )


def run_noiseprint_analysis(
    evidence_path: str,
    *,
    on_progress: ProgressFn = None,
) -> NoiseprintAnalysisResult:
    """Extract noiseprint and run GRIP-UNINA blind forgery localization."""

    def _run(device):
        return _run_noiseprint_on_device(evidence_path, on_progress=on_progress, device=device)

    result, _device = run_with_device_fallback(_run)
    return result
