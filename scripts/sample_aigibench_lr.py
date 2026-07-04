#!/usr/bin/env python3
"""Sample selected AIGIBench test subsets for LR out-of-domain evaluation."""

from __future__ import annotations

import argparse
import random
import shutil
import zipfile
from collections import Counter
from pathlib import Path

from huggingface_hub import hf_hub_download

from lr_dataset_utils import iter_image_files, materialize_file, reset_dir, safe_name, write_json, write_manifest

REPO_ID = "HorizonTEL/AIGIBench"
DATASET = "AIGIBench"


def _download_zip(raw_dir: Path, subset: str) -> Path:
    filename = f"test/{subset}.zip"
    path = Path(
        hf_hub_download(
            repo_id=REPO_ID,
            repo_type="dataset",
            filename=filename,
            local_dir=str(raw_dir),
            resume_download=True,
        )
    )
    return path


def _extract(zip_path: Path, extract_dir: Path) -> None:
    marker = extract_dir / ".extracted"
    if marker.exists():
        return
    extract_dir.mkdir(parents=True, exist_ok=True)
    print(f"Extracting {zip_path}", flush=True)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(extract_dir)
    marker.write_text("ok\n", encoding="utf-8")


def _classify(path: Path) -> tuple[str, int] | None:
    parts = {part.lower() for part in path.parts}
    if "0_real" in parts or "real" in parts:
        return "real", 0
    if "1_fake" in parts or "fake" in parts:
        return "fake", 1
    return None


def _sample_subset(
    *,
    subset: str,
    extract_dir: Path,
    out_dir: Path,
    per_class: int,
    rng: random.Random,
) -> list[dict[str, object]]:
    real_files = []
    fake_files = []
    for image in iter_image_files(extract_dir):
        label = _classify(image)
        if label is None:
            continue
        if label[1] == 1:
            fake_files.append(image)
        else:
            real_files.append(image)
    rng.shuffle(real_files)
    rng.shuffle(fake_files)

    rows = []
    for label_name, y_fake, files in (("real", 0, real_files[:per_class]), ("fake", 1, fake_files[:per_class])):
        for path in files:
            rows.append(
                materialize_file(
                    out_dir=out_dir,
                    purpose="out_domain_test",
                    dataset=DATASET,
                    generator=subset if y_fake else f"{subset}_real",
                    generator_id=subset if y_fake else 0,
                    label=label_name,
                    y_fake=y_fake,
                    source_split="test",
                    source_id=safe_name(path.stem),
                    source_path=path,
                )
            )
    if len(real_files) < per_class or len(fake_files) < per_class:
        print(
            f"WARNING {subset}: requested {per_class}/class, available real={len(real_files)} fake={len(fake_files)}",
            flush=True,
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="/home/bfl-pcf/datasets/aigibench_lr_sample")
    parser.add_argument("--raw-dir", default="/home/bfl-pcf/datasets/aigibench_raw")
    parser.add_argument("--subsets", default="CommunityAI,SocialRF,FLUX1-dev,SD3,DALLE-3,Midjourney")
    parser.add_argument("--per-class", type=int, default=150)
    parser.add_argument("--seed", type=int, default=20260629)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--drop-extracted", action="store_true")
    args = parser.parse_args()

    out_dir = Path(args.out)
    raw_dir = Path(args.raw_dir)
    reset_dir(out_dir, args.force)
    raw_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)

    rows = []
    subsets = [item.strip() for item in args.subsets.split(",") if item.strip()]
    for subset in subsets:
        zip_path = _download_zip(raw_dir, subset)
        extract_dir = raw_dir / "test" / f"{subset}_extracted"
        _extract(zip_path, extract_dir)
        rows.extend(_sample_subset(subset=subset, extract_dir=extract_dir, out_dir=out_dir, per_class=args.per_class, rng=rng))
        if args.drop_extracted:
            shutil.rmtree(extract_dir, ignore_errors=True)

    write_manifest(out_dir / "manifest.csv", rows)
    write_json(
        out_dir / "summary.json",
        {
            "dataset": DATASET,
            "repo_id": REPO_ID,
            "subsets": subsets,
            "rows": len(rows),
            "counts_by_label": dict(Counter(row["label"] for row in rows)),
            "counts_by_generator": dict(Counter(row["generator"] for row in rows)),
        },
    )
    print(f"Wrote {len(rows)} rows to {out_dir / 'manifest.csv'}")


if __name__ == "__main__":
    main()
