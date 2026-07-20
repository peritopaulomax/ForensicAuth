#!/usr/bin/env python3
"""Download MoE-FFD pretrained checkpoint from Hugging Face and validate integrity.

Source: https://huggingface.co/luobo91/MoE-FFD
Target: models/moe_ffd/MoE-FFD.tar

WARNING: the HF file published 2026-07-11 is a mid-training ``models_params_14.tar``
with MoE gates still at ~0. The forensic pipeline WILL reject it until the authors
publish ``model_params_best_*.pkl`` (see vendor/MoE-FFD/train.py).

Usage:
  conda activate va-suite
  python scripts/download_moe_ffd_weights.py
  python scripts/download_moe_ffd_weights.py --force
  python scripts/download_moe_ffd_weights.py --validate-only
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _validate(dest: Path) -> int:
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "src" / "backend"))
    from core.legacy.moe_ffd.runtime import clear_checkpoint_inspect_cache, inspect_moe_ffd_checkpoint

    clear_checkpoint_inspect_cache()
    report = inspect_moe_ffd_checkpoint(dest)
    print("Checkpoint integrity:")
    for k in (
        "ok",
        "format",
        "epoch",
        "has_optimizer",
        "n_keys",
        "gate_absmax",
        "noise_absmax",
        "head_weight_absmax",
    ):
        print(f"  {k}: {report.get(k)}")
    if not report.get("ok"):
        print(f"INVALID: {report.get('reason')}", file=sys.stderr)
        return 2
    print("OK: checkpoint passed MoE gate health check.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Download MoE-FFD weights from Hugging Face")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "models" / "moe_ffd",
        help="Output directory (default: models/moe_ffd)",
    )
    parser.add_argument("--force", action="store_true", help="Re-download even if file exists")
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Only run integrity check on existing file",
    )
    args = parser.parse_args()
    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / "MoE-FFD.tar"

    if args.validate_only:
        if not dest.is_file():
            print(f"Missing: {dest}", file=sys.stderr)
            return 1
        return _validate(dest)

    if dest.is_file() and dest.stat().st_size > 100_000_000 and not args.force:
        print(f"Already present: {dest} ({dest.stat().st_size} bytes)")
        return _validate(dest)

    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        print("huggingface_hub required: pip install huggingface_hub", file=sys.stderr)
        return 1

    print("Downloading luobo91/MoE-FFD MoE-FFD.tar …")
    path = hf_hub_download(
        repo_id="luobo91/MoE-FFD",
        filename="MoE-FFD.tar",
        local_dir=str(out_dir),
    )
    print(f"Saved: {path}")
    return _validate(Path(path) if Path(path).name == "MoE-FFD.tar" else dest)


if __name__ == "__main__":
    raise SystemExit(main())
