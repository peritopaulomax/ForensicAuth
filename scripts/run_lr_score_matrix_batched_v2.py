#!/usr/bin/env python3
"""Batched scorer for LR calibration matrices (v2).

Same as run_lr_score_matrix_batched.py, but always includes the SAFE detector
in addition to ai_image_detector_deploy, sdxl_flux_detector_v1_1, bfree and
corvi2023.  SAFE is evaluated one image at a time using 4 tiles (central crop
plus 3 additional quadrant crops) with logit averaging.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import torch
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "src" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from core.gpu_inference import device_display_label, resolve_inference_device  # noqa: E402
from core.legacy.bfree import bfree_pipeline  # noqa: E402
from core.legacy.safe import safe_pipeline  # noqa: E402
from core.legacy.synthetic_image_detection import pipeline as sid  # noqa: E402
from core.legacy.truebees_clip_d import clipd_pipeline  # noqa: E402

DETECTORS = (
    "ai_image_detector_deploy",
    "sdxl_flux_detector_v1_1",
    "bfree",
    "corvi2023",
    "safe",
)


def _read_manifest(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    dataset_fallback = "GenImage" if "genimage" in path.as_posix().lower() else path.parent.name
    for row in rows:
        row["_manifest"] = str(path)
        row["_root"] = str(path.parent)
        if not row.get("dataset"):
            row["dataset"] = dataset_fallback
    return rows


def _input_path(row: dict[str, str]) -> Path:
    return Path(row["_root"]) / row["dest_relative"]


def _y_fake(row: dict[str, str]) -> int:
    value = row.get("y_fake")
    if value not in (None, ""):
        return int(value)
    return 1 if row.get("label") in {"fake", "ai"} else 0


def _init_output_row(row: dict[str, str], path: Path) -> dict[str, Any]:
    out = {
        "dataset": row.get("dataset", ""),
        "purpose": row.get("purpose", ""),
        "generator": row.get("generator", ""),
        "generator_id": row.get("generator_id", ""),
        "label": row.get("label", ""),
        "y_fake": _y_fake(row),
        "source_split": row.get("source_split", ""),
        "source_id": row.get("source_id", ""),
        "dest_relative": row.get("dest_relative", ""),
        "image_path": str(path),
        "image_sha256": row.get("sha256", ""),
        "augmentation": row.get("augmentation", ""),
        "error": "",
        "elapsed_seconds": "",
    }
    for detector in DETECTORS:
        out[f"{detector}_fake_prob"] = ""
        out[f"{detector}_real_prob"] = ""
        out[f"{detector}_raw_score"] = ""
        out[f"{detector}_decision"] = ""
        out[f"{detector}_device"] = ""
    return out


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else ["dataset", "purpose", "label", "y_fake", "error"]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _softmax(logits: np.ndarray) -> np.ndarray:
    exp = np.exp(logits - np.max(logits, axis=1, keepdims=True))
    return exp / np.sum(exp, axis=1, keepdims=True)


def _set_prob(row: dict[str, Any], detector: str, fake_prob: float, raw_score: float | None, device: str) -> None:
    fake_prob = min(max(float(fake_prob), 1e-8), 1.0 - 1e-8)
    row[f"{detector}_fake_prob"] = f"{fake_prob:.8f}"
    row[f"{detector}_real_prob"] = f"{1.0 - fake_prob:.8f}"
    row[f"{detector}_raw_score"] = "" if raw_score is None else f"{raw_score:.8f}"
    row[f"{detector}_decision"] = "AI" if fake_prob >= 0.5 else "REAL"
    row[f"{detector}_device"] = device


def _score_hf(images: list[Image.Image], output_rows: list[dict[str, Any]], device_label: str, batch_size: int) -> None:
    sid._ensure_models_loaded()
    assert sid._DETECTION_MODELS is not None

    model1 = sid._DETECTION_MODELS["model_1"]["model"]
    predictions = model1([sid._as_rgb(image) for image in images], top_k=5, batch_size=batch_size)
    for out_row, prediction in zip(output_rows, predictions):
        scores = {item["label"]: item["score"] for item in prediction}
        fake = 0.5
        for label, score in scores.items():
            if label.lower() in {"artificial", "ai", "fake", "deepfake", "ai_gen", "aigenerated"}:
                fake = float(score)
                break
        _set_prob(out_row, "ai_image_detector_deploy", fake, None, device_label)

    model4_info = sid._DETECTION_MODELS["model_4"]
    infer_fn = model4_info["model"]
    model, feature_extractor, dev = infer_fn.__defaults__
    inputs = feature_extractor([sid._as_rgb(image) for image in images], return_tensors="pt").to(dev)
    with torch.no_grad():
        logits = model(**inputs).logits.detach().cpu().numpy()
    probs = _softmax(logits)
    for out_row, prob in zip(output_rows, probs):
        scores = {sid.CLASS_NAMES["model_4"][idx]: prob[idx] for idx in range(len(prob))}
        fake = 0.5
        for label, score in scores.items():
            if label.lower() in {"artificial", "ai", "fake", "deepfake", "ai_gen", "aigenerated"}:
                fake = float(score)
                break
        _set_prob(out_row, "sdxl_flux_detector_v1_1", fake, None, device_label)


def _score_bfree(images: list[Image.Image], output_rows: list[dict[str, Any]], device: torch.device, device_label: str) -> None:
    model, transform = bfree_pipeline._load_model(device)
    for image, out_row in zip(images, output_rows):
        tensor = transform(image.convert("RGB")).unsqueeze(0).to(device)
        with torch.no_grad():
            score = float(model(tensor).detach().cpu().numpy().reshape(-1)[0])
        _set_prob(out_row, "bfree", bfree_pipeline._sigmoid(float(score)), float(score), device_label)


def _score_corvi(images: list[Image.Image], output_rows: list[dict[str, Any]], device: torch.device, device_label: str) -> None:
    model, transform = clipd_pipeline._load_model(device, clipd_pipeline.CORVI2023_MODEL_NAME)
    for image, out_row in zip(images, output_rows):
        tiles = clipd_pipeline._extract_tiles(image.convert("RGB"), clipd_pipeline.CORVI2023_TILE_SIZE)
        llrs: list[float] = []
        for tile in tiles:
            tensor = transform(tile).unsqueeze(0).to(device)
            with torch.no_grad():
                output = model(tensor).detach().cpu().numpy()
            llrs.append(clipd_pipeline._output_to_llr(output))
        llr = float(sum(llrs) / len(llrs))
        _set_prob(out_row, "corvi2023", clipd_pipeline._sigmoid_from_llr(llr), llr, device_label)


def _score_safe(images: list[Image.Image], output_rows: list[dict[str, Any]], device: torch.device, device_label: str) -> None:
    for image, out_row in zip(images, output_rows):
        prob = safe_pipeline.infer_safe_from_pil_tiled(image, device, n_tiles=4)
        _set_prob(out_row, "safe", prob, None, device_label)


def _chunks(rows: list[dict[str, str]], size: int):
    for start in range(0, len(rows), size):
        yield start, rows[start : start + size]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", action="append", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    rows: list[dict[str, str]] = []
    for manifest in args.manifest:
        rows.extend(_read_manifest(Path(manifest)))
    if args.limit:
        rows = rows[: args.limit]

    out_path = Path(args.out)
    existing: list[dict[str, Any]] = []
    done = set()
    if args.resume and out_path.exists():
        with out_path.open(encoding="utf-8") as fh:
            existing = list(csv.DictReader(fh))
        done = {row.get("image_path", "") for row in existing if row.get("image_path")}

    pending = [row for row in rows if str(_input_path(row)) not in done]
    output_rows = existing[:]
    device = resolve_inference_device()
    device_label = device_display_label(device.type)
    start_all = time.time()

    for start_idx, chunk in _chunks(pending, args.batch_size):
        batch_start = time.time()
        images: list[Image.Image] = []
        batch_rows: list[dict[str, Any]] = []
        for row in chunk:
            path = _input_path(row)
            out_row = _init_output_row(row, path)
            try:
                with Image.open(path) as image:
                    images.append(image.convert("RGB").copy())
                batch_rows.append(out_row)
            except Exception as exc:
                out_row["error"] = repr(exc)
                output_rows.append(out_row)
        if batch_rows:
            try:
                _score_hf(images, batch_rows, device_label, args.batch_size)
                _score_bfree(images, batch_rows, device, device_label)
                _score_corvi(images, batch_rows, device, device_label)
                _score_safe(images, batch_rows, device, device_label)
            except RuntimeError as exc:
                if args.batch_size > 1 and "out of memory" in str(exc).lower():
                    raise RuntimeError("GPU OOM: rerun with a smaller --batch-size and --resume") from exc
                for out_row in batch_rows:
                    out_row["error"] = repr(exc)
            elapsed = time.time() - batch_start
            for out_row in batch_rows:
                out_row["elapsed_seconds"] = f"{elapsed / max(len(batch_rows), 1):.3f}"
            output_rows.extend(batch_rows)
        _write_csv(out_path, output_rows)
        processed = min(start_idx + len(chunk), len(pending))
        print(f"Processed pending {processed}/{len(pending)} total_rows={len(output_rows)}", flush=True)

    summary = {
        "out": str(out_path),
        "rows": len(output_rows),
        "errors": sum(1 for row in output_rows if row.get("error")),
        "batch_size": args.batch_size,
        "elapsed_seconds": time.time() - start_all,
    }
    out_path.with_suffix(".summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    os.environ.setdefault("PYTHONHASHSEED", "0")
    main()
