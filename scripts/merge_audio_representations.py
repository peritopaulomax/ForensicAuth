#!/usr/bin/env python3
"""Merge original and augmented representation extracts into unified matrix."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "backend"))

from core.latent_typicality.representations_utils import ORIGINAL_AUGMENTATION_TAG


def load_config(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def merge_representations(
    *,
    originals_csv: Path,
    augmented_csv: Path,
    out_csv: Path,
) -> dict[str, int | str]:
    frames: list[pd.DataFrame] = []
    for path, kind in ((originals_csv, "originals"), (augmented_csv, "augmented")):
        if not path.is_file():
            raise FileNotFoundError(f"Representations {kind} nao encontrado: {path}")
        part = pd.read_csv(path, low_memory=False)
        if "error" in part.columns:
            part = part[part["error"].fillna("").eq("")].copy()
        part["merge_source"] = kind
        frames.append(part)

    merged = pd.concat(frames, ignore_index=True)
    if "augmentation" in merged.columns:
        merged["augmentation"] = merged["augmentation"].fillna("").astype(str)
        merged.loc[merged["augmentation"].eq(""), "augmentation"] = ORIGINAL_AUGMENTATION_TAG
    merged = merged.drop_duplicates(subset=["sample_id"], keep="last")
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(out_csv, index=False)
    summary = {
        "out_csv": str(out_csv),
        "rows": int(len(merged)),
        "original_rows": int(merged["merge_source"].eq("originals").sum()) if "merge_source" in merged.columns else 0,
        "augmented_rows": int(merged["merge_source"].eq("augmented").sum()) if "merge_source" in merged.columns else 0,
    }
    out_csv.with_suffix(".summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/audio_spoofing_typicality.yaml")
    args = parser.parse_args()
    cfg = load_config(ROOT / args.config)
    originals = ROOT / cfg.get("originals_embeddings_dir", "outputs/lr_calibration/audio_spoofing/representations/originals") / "representations.csv"
    augmented = ROOT / cfg.get("augmented_embeddings_dir", "outputs/lr_calibration/audio_spoofing/representations/augmented") / "representations.csv"
    out_csv = ROOT / cfg.get("merged_representations_csv", "outputs/lr_calibration/audio_spoofing/representations/representations.csv")
    summary = merge_representations(originals_csv=originals, augmented_csv=augmented, out_csv=out_csv)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
