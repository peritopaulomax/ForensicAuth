#!/usr/bin/env python3
"""Sample Defactify/MS COCOAI for synthetic-image LR calibration."""

from __future__ import annotations

import argparse
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
from huggingface_hub import HfApi, hf_hub_download

from lr_dataset_utils import image_suffix, materialize_bytes, reset_dir, write_json, write_manifest

REPO_ID = "Rajarshi-Roy-research/Defactify_Image_Dataset"
DATASET = "Defactify_MS_COCOAI"
GENERATOR_NAMES = {
    0: "Real",
    1: "SD2.1",
    2: "SDXL",
    3: "SD3",
    4: "DALL-E_3",
    5: "Midjourney_v6",
}


def _column_name(schema_names: list[str], candidates: tuple[str, ...]) -> str:
    lowered = {name.lower(): name for name in schema_names}
    for candidate in candidates:
        if candidate.lower() in lowered:
            return lowered[candidate.lower()]
    raise RuntimeError(f"Cannot find any of columns {candidates}; available={schema_names}")


def _image_bytes(value: Any) -> tuple[bytes, str]:
    if isinstance(value, dict):
        data = value.get("bytes")
        if data is None and value.get("path"):
            data = Path(value["path"]).read_bytes()
        if data is None:
            raise RuntimeError("Image row has no bytes/path")
        return bytes(data), str(value.get("path") or "")
    if isinstance(value, (bytes, bytearray)):
        return bytes(value), ""
    raise RuntimeError(f"Unsupported image payload: {type(value)!r}")


def _download_parquets(raw_dir: Path, max_shards: int | None) -> list[Path]:
    api = HfApi()
    files = sorted(
        f for f in api.list_repo_files(repo_id=REPO_ID, repo_type="dataset") if f.endswith(".parquet")
    )
    if not files:
        raise RuntimeError(f"No parquet files found in {REPO_ID}")
    selected = files if max_shards is None else files[:max_shards]
    paths = []
    for filename in selected:
        paths.append(
            Path(
                hf_hub_download(
                    repo_id=REPO_ID,
                    repo_type="dataset",
                    filename=filename,
                    local_dir=str(raw_dir),
                )
            )
        )
    return paths


def _collect_candidates(parquets: list[Path]) -> dict[tuple[str, int], list[dict[str, Any]]]:
    candidates: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for parquet in parquets:
        pf = pq.ParquetFile(parquet)
        names = pf.schema_arrow.names
        image_col = _column_name(names, ("image", "Image", "img"))
        label_col = _column_name(names, ("Label_A", "label", "Label", "binary_label"))
        generator_col = _column_name(names, ("Label_B", "generator", "Generator", "source"))
        for batch in pf.iter_batches(columns=[image_col, label_col, generator_col], batch_size=256):
            images = batch.column(0).to_pylist()
            labels = batch.column(1).to_pylist()
            generators = batch.column(2).to_pylist()
            for idx, (image, label, generator) in enumerate(zip(images, labels, generators)):
                y_fake = int(label)
                gen_id = int(generator)
                group = ("fake", gen_id) if y_fake == 1 else ("real", 0)
                candidates[group].append(
                    {
                        "image": image,
                        "y_fake": y_fake,
                        "generator_id": gen_id,
                        "source_split": parquet.stem,
                        "source_id": f"{parquet.stem}_r{idx:06d}",
                    }
                )
    return candidates


def _select(candidates: dict[tuple[str, int], list[dict[str, Any]]], seed: int, per_fake: dict[str, int]) -> list[tuple[str, dict[str, Any]]]:
    rng = random.Random(seed)
    selected: list[tuple[str, dict[str, Any]]] = []
    shortages = []
    for gen_id in range(1, 6):
        rows = candidates.get(("fake", gen_id), [])
        rng.shuffle(rows)
        cursor = 0
        for purpose, count in per_fake.items():
            chunk = rows[cursor : cursor + count]
            if len(chunk) < count:
                shortages.append((GENERATOR_NAMES[gen_id], purpose, len(chunk), count))
            selected.extend((purpose, row) for row in chunk)
            cursor += count
    real_rows = candidates.get(("real", 0), [])
    rng.shuffle(real_rows)
    cursor = 0
    for purpose, fake_count in per_fake.items():
        count = fake_count * 5
        chunk = real_rows[cursor : cursor + count]
        if len(chunk) < count:
            shortages.append(("Real", purpose, len(chunk), count))
        selected.extend((purpose, row) for row in chunk)
        cursor += count
    if shortages:
        available = {str(k): len(v) for k, v in candidates.items()}
        raise RuntimeError(f"Insufficient Defactify rows: {shortages}; available={available}")
    return selected


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="/home/bfl-pcf/datasets/defactify_lr_sample")
    parser.add_argument("--raw-dir", default="/home/bfl-pcf/datasets/defactify_raw")
    parser.add_argument("--seed", type=int, default=20260629)
    parser.add_argument("--train-per-fake", type=int, default=120)
    parser.add_argument("--validation-per-fake", type=int, default=40)
    parser.add_argument("--test-per-fake", type=int, default=40)
    parser.add_argument("--max-shards", type=int, default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    out_dir = Path(args.out)
    raw_dir = Path(args.raw_dir)
    reset_dir(out_dir, args.force)
    raw_dir.mkdir(parents=True, exist_ok=True)

    parquets = _download_parquets(raw_dir, args.max_shards)
    candidates = _collect_candidates(parquets)
    per_fake = {
        "calibration_train": args.train_per_fake,
        "validation": args.validation_per_fake,
        "in_domain_test": args.test_per_fake,
    }
    selected = _select(candidates, args.seed, per_fake)

    rows = []
    for purpose, row in selected:
        y_fake = int(row["y_fake"])
        gen_id = int(row["generator_id"]) if y_fake == 1 else 0
        generator = GENERATOR_NAMES.get(gen_id, f"generator_{gen_id}")
        label = "fake" if y_fake else "real"
        data, source_path = _image_bytes(row["image"])
        rows.append(
            materialize_bytes(
                out_dir=out_dir,
                purpose=purpose,
                dataset=DATASET,
                generator=generator,
                generator_id=gen_id,
                label=label,
                y_fake=y_fake,
                source_split=row["source_split"],
                source_id=row["source_id"],
                source_path=source_path,
                data=data,
                suffix=image_suffix(source_path),
            )
        )

    write_manifest(out_dir / "manifest.csv", rows)
    summary = {
        "dataset": DATASET,
        "repo_id": REPO_ID,
        "raw_parquets": [str(p) for p in parquets],
        "rows": len(rows),
        "counts_by_purpose_label": {
            f"{purpose}:{label}": count for (purpose, label), count in Counter((r["purpose"], r["label"]) for r in rows).items()
        },
        "counts_by_generator": dict(Counter(r["generator"] for r in rows if r["label"] == "fake")),
    }
    write_json(out_dir / "summary.json", summary)
    print(f"Wrote {len(rows)} rows to {out_dir / 'manifest.csv'}")


if __name__ == "__main__":
    main()
