"""Compute SAFE scores for every image in the synthetic-image reference score matrix.

Reads the existing LR calibration CSV, runs SAFE (KDD'25) on each image_path,
and writes an updated CSV with safe_* columns appended.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

import pandas as pd
from PIL import Image

# Make backend modules importable when running from project root.
BACKEND_ROOT = Path(__file__).resolve().parents[1] / "src" / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.legacy.safe.safe_pipeline import clear_safe_model_cache, infer_safe_from_pil  # noqa: E402
from core.gpu_inference import resolve_inference_device, run_with_device_fallback  # noqa: E402

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compute SAFE reference scores")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("outputs/lr_calibration/score_matrices/lr_scores_balanced_full.csv"),
        help="Input score matrix CSV",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output CSV (default: overwrite input with .new suffix until verified)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="Report progress every N rows",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process only first N rows (for testing)",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    input_path = args.input
    output_path = args.output or input_path.with_suffix(".safe_new.csv")

    if not input_path.is_file():
        logger.error("Input CSV not found: %s", input_path)
        return 1

    df = pd.read_csv(input_path, low_memory=False)
    if args.limit is not None:
        df = df.head(args.limit).copy()

    # Drop any pre-existing safe columns to avoid duplication.
    safe_cols = [c for c in df.columns if c.startswith("safe_")]
    if safe_cols:
        logger.info("Removing existing SAFE columns: %s", safe_cols)
        df = df.drop(columns=safe_cols)

    total = len(df)
    logger.info("Processing %d images with SAFE...", total)

    device = resolve_inference_device()
    logger.info("Inference device: %s", device)

    safe_fake_probs: list[float] = []
    safe_real_probs: list[float] = []
    safe_raw_scores_list: list[str] = []
    safe_decisions: list[str] = []
    safe_devices: list[str] = []
    safe_errors: list[str] = []
    safe_elapsed: list[float] = []

    for idx, image_path in enumerate(df["image_path"], start=1):
        start = time.perf_counter()
        try:
            image = Image.open(image_path).convert("RGB")

            def _run(dev):
                return infer_safe_from_pil(image, dev)

            prob_fake, used_device = run_with_device_fallback(
                _run,
                on_fallback=clear_safe_model_cache,
            )
            prob_real = 1.0 - prob_fake
            decision = "AI" if prob_fake > 0.5 else "REAL"
            raw_score = f"{prob_fake:.4f}"
            device_label = used_device.type if hasattr(used_device, "type") else str(used_device)
            error = ""
        except Exception as exc:
            logger.warning("SAFE failed for %s: %s", image_path, exc)
            prob_fake = 0.5
            prob_real = 0.5
            decision = "Incerto"
            raw_score = ""
            device_label = ""
            error = str(exc)

        elapsed = time.perf_counter() - start
        safe_fake_probs.append(prob_fake)
        safe_real_probs.append(prob_real)
        safe_raw_scores_list.append(raw_score)
        safe_decisions.append(decision)
        safe_devices.append(device_label)
        safe_errors.append(error)
        safe_elapsed.append(elapsed)

        if idx % args.batch_size == 0 or idx == total:
            logger.info("SAFE progress: %d/%d (%.1f%%)", idx, total, 100.0 * idx / total)

    df["safe_fake_prob"] = safe_fake_probs
    df["safe_real_prob"] = safe_real_probs
    df["safe_raw_score"] = safe_raw_scores_list
    df["safe_decision"] = safe_decisions
    df["safe_device"] = safe_devices
    df["safe_error"] = safe_errors
    df["safe_elapsed_seconds"] = safe_elapsed

    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    logger.info("Wrote updated score matrix to %s", output_path)

    # Print quick stats.
    valid = df[df["safe_error"].eq("")]
    logger.info(
        "SAFE stats: processed=%d, errors=%d, mean_fake_prob=%.4f",
        len(df),
        len(df) - len(valid),
        valid["safe_fake_prob"].mean() if len(valid) else float("nan"),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
