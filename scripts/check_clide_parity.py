#!/usr/bin/env python3
"""Compare ForensicAuth CLIDE likelihood with the vendored official computation."""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import torch
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "src" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from core.legacy.clide.clide_pipeline import clear_clide_model_cache, infer_clide_from_pil
from core.legacy.clide.clide_runtime import (
    clide_clip_cache_dir,
    clide_runtime_status,
    resolve_rep_matrix,
    resolve_whitening_matrix,
)
from core.legacy.clide.clide_vendor import load_detection_module


def _direct_vendor_likelihood(
    image: Image.Image,
    device: torch.device,
    *,
    mode: str,
    k: int,
    m: int,
) -> float:
    import clip

    detection = load_detection_module()
    model, preprocess = clip.load(
        "ViT-L/14",
        device=device.type,
        download_root=str(clide_clip_cache_dir()),
    )
    model.eval()
    image_tensor = preprocess(image.convert("RGB")).unsqueeze(0).to(device)
    with torch.no_grad():
        embedding = model.encode_image(image_tensor).squeeze(0).to(device, dtype=torch.float32)
    if mode == "local":
        rep_path = resolve_rep_matrix("general")
        if rep_path is None:
            raise RuntimeError("Representative matrix CLIDE ausente")
        rep_mat = torch.load(str(rep_path), map_location=device, weights_only=False).to(device)
        similarities = torch.cosine_similarity(embedding, rep_mat, dim=1)
        top_k_indices = torch.topk(similarities, k=min(k, int(rep_mat.shape[0])), largest=True).indices
        selected_rep = rep_mat[top_k_indices]
        _, w_mat = detection.sphx(selected_rep, m=m)
        w_mean = selected_rep.mean(dim=0)
        dimensions = m
    else:
        w_path = resolve_whitening_matrix("general")
        if w_path is None:
            raise RuntimeError("Matriz CLIDE ausente")
        w_mat, w_mean = torch.load(str(w_path), map_location=device, weights_only=False)
        w_mat = w_mat.to(device)
        w_mean = w_mean.to(device)
        dimensions = int(w_mat.shape[1])
    log_const = 0.5 * dimensions * torch.log(torch.tensor(2 * math.pi, device=device))
    whitened_embedding = (embedding - w_mean) @ w_mat
    return float((-(log_const + 0.5 * whitened_embedding.norm() ** 2)).detach().cpu().item())


def compare(image_path: Path, device: torch.device, tolerance: float, mode: str, k: int, m: int) -> int:
    ok, reason = clide_runtime_status()
    if not ok:
        print(f"CLIDE indisponivel: {reason}")
        return 2

    image = Image.open(image_path).convert("RGB")
    clear_clide_model_cache()
    ours = infer_clide_from_pil(image, device, mode=mode, k=k, m=m).likelihood
    clear_clide_model_cache()
    vendor = _direct_vendor_likelihood(image, device, mode=mode, k=k, m=m)
    diff = abs(ours - vendor)
    print(f"image={image_path}")
    print(f"device={device.type}")
    print(f"mode={mode}")
    print(f"clip_cache={clide_clip_cache_dir()}")
    print(f"forensicauth_likelihood={ours:.12f}")
    print(f"vendor_likelihood={vendor:.12f}")
    print(f"abs_diff={diff:.12g}")
    return 0 if diff <= tolerance else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path)
    parser.add_argument("--device", choices=["cpu", "cuda"], default="cpu")
    parser.add_argument("--mode", choices=["local", "global"], default="local")
    parser.add_argument("--k", type=int, default=500)
    parser.add_argument("--m", type=int, default=400)
    parser.add_argument("--tolerance", type=float, default=1e-6)
    args = parser.parse_args()
    if args.device == "cuda" and not torch.cuda.is_available():
        raise SystemExit("CUDA indisponivel")
    return compare(args.image, torch.device(args.device), args.tolerance, args.mode, args.k, args.m)


if __name__ == "__main__":
    raise SystemExit(main())
