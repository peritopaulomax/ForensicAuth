#!/usr/bin/env python3
"""Compare ForensicAuth DeeCLIP score with the vendored official call."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import torch
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "src" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from core.legacy.deeclip.deeclip_pipeline import clear_deeclip_model_cache, infer_deeclip_from_pil
from core.legacy.deeclip.deeclip_runtime import (
    deeclip_runtime_status,
    resolve_checkpoint,
    resolve_clip_snapshot_path,
)
from core.legacy.deeclip.deeclip_vendor import load_deeclip_class

LAYER_INDICES = [1, 3, 5, 8, 10, 13, 15, 17, 19, 21, 22, 23]


def _direct_vendor_score(image: Image.Image, device: torch.device) -> float:
    clip_path = resolve_clip_snapshot_path()
    ckpt_path = resolve_checkpoint()
    if clip_path is None or ckpt_path is None:
        raise RuntimeError("Assets DeeCLIP ausentes")

    DeeCLIP = load_deeclip_class()
    model = DeeCLIP(model_name=str(clip_path), layer_indices=LAYER_INDICES).to(device)
    try:
        state = torch.load(str(ckpt_path), map_location=device, weights_only=False)
    except TypeError:
        state = torch.load(str(ckpt_path), map_location=device)
    model.load_state_dict(state, strict=False)
    model.eval()

    from transformers import CLIPImageProcessor

    processor = CLIPImageProcessor.from_pretrained(str(clip_path), local_files_only=True)
    tensor = processor(images=image.convert("RGB"), return_tensors="pt")["pixel_values"].to(device)
    with torch.no_grad():
        _, _, outputs = model(tensor, train=False)
        return float(torch.sigmoid(outputs).float().cpu().reshape(-1)[0].item())


def compare(image_path: Path, device: torch.device, tolerance: float) -> int:
    ok, reason = deeclip_runtime_status()
    if not ok:
        print(f"DeeCLIP indisponivel: {reason}")
        return 2

    image = Image.open(image_path).convert("RGB")
    clear_deeclip_model_cache()
    ours = infer_deeclip_from_pil(image, device)
    clear_deeclip_model_cache()
    vendor = _direct_vendor_score(image, device)
    diff = abs(ours - vendor)

    print(f"image={image_path}")
    print(f"device={device.type}")
    print(f"forensicauth={ours:.12f}")
    print(f"vendor={vendor:.12f}")
    print(f"abs_diff={diff:.12g}")
    return 0 if diff <= tolerance else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path)
    parser.add_argument("--device", choices=["cpu", "cuda"], default="cpu")
    parser.add_argument("--tolerance", type=float, default=1e-8)
    args = parser.parse_args()
    if args.device == "cuda" and not torch.cuda.is_available():
        raise SystemExit("CUDA indisponivel")
    return compare(args.image, torch.device(args.device), args.tolerance)


if __name__ == "__main__":
    raise SystemExit(main())
