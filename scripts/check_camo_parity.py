#!/usr/bin/env python3
"""Compare ForensicAuth CAMO score with the vendored BitMind CAMO detector."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import torch
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "src" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from core.legacy.camo.camo_pipeline import clear_camo_model_cache, infer_camo_from_pil
from core.legacy.camo.camo_runtime import camo_runtime_status, camo_vendor_dir
from core.legacy.camo.camo_vendor import bootstrap_camo_modules, camo_vendor_context


def _as_score(value: object) -> float:
    return float(np.asarray(value, dtype=np.float64).reshape(-1)[0])


def _direct_vendor_score(image: Image.Image, device: torch.device) -> float:
    with camo_vendor_context():
        bootstrap_camo_modules(camo_vendor_dir())
        import sys as _sys

        CAMOImageDetector = _sys.modules[
            "base_miner.deepfake_detectors.camo_detector"
        ].CAMOImageDetector
        detector = CAMOImageDetector(device="cuda" if device.type == "cuda" else "cpu")
        score = detector(image.convert("RGB"))
        return _as_score(score)


def compare(image_path: Path, device: torch.device, tolerance: float) -> int:
    ok, reason = camo_runtime_status()
    if not ok:
        print(f"CAMO indisponivel: {reason}", file=sys.stderr)
        return 2

    image = Image.open(image_path).convert("RGB")
    clear_camo_model_cache()
    vendor = _direct_vendor_score(image, device)
    clear_camo_model_cache()
    ours = infer_camo_from_pil(image, device)
    diff = abs(ours - vendor)

    print(f"image={image_path}")
    print(f"device={device.type}")
    print(f"vendor={vendor:.12f}")
    print(f"forensicauth={ours:.12f}")
    print(f"abs_diff={diff:.12g}")
    print(f"tolerance={tolerance:.12g}")
    return 0 if diff <= tolerance else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path, help="Imagem para comparar")
    parser.add_argument("--device", choices=["cpu", "cuda"], default="cpu")
    parser.add_argument("--tolerance", type=float, default=1e-8)
    args = parser.parse_args()

    if not args.image.is_file():
        print(f"Imagem nao encontrada: {args.image}", file=sys.stderr)
        return 2
    if args.device == "cuda" and not torch.cuda.is_available():
        print("CUDA indisponivel neste ambiente.", file=sys.stderr)
        return 2
    return compare(args.image, torch.device(args.device), args.tolerance)


if __name__ == "__main__":
    raise SystemExit(main())
