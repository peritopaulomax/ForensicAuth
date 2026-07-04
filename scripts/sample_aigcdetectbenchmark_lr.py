#!/usr/bin/env python3
"""Sample AIGCDetectBenchmark for synthetic-image LR calibration."""

from __future__ import annotations

import argparse
import random
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
from huggingface_hub import HfApi, hf_hub_download

from lr_dataset_utils import image_suffix, materialize_bytes, reset_dir, write_json, write_manifest

REPO_ID = "TheKernel01/AIGC-Detection-Benchmark"
DATASET = "AIGCDetectBenchmark"

GEN_NAMES = {
    0: "Real",
    1: "ADM",
    2: "BigGAN",
    3: "CycleGAN",
    4: "DALLE2",
    5: "GauGAN",
    6: "GLIDE",
    7: "Midjourney",
    8: "ProGAN",
    9: "SD14",
    10: "SD15",
    11: "SDXL",
    12: "StarGAN",
    13: "StyleGAN",
    14: "StyleGAN2",
    15: "VQDM",
    16: "WhichFaceIsReal",
    17: "Wukong",
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


def _list_parquet_files() -> list[str]:
    api = HfApi()
    return sorted(
        f for f in api.list_repo_files(repo_id=REPO_ID, repo_type="dataset") if f.endswith(".parquet")
    )


def _download_parquets(raw_dir: Path, max_shards: int | None, min_shards: int = 0) -> list[Path]:
    files = _list_parquet_files()
    if not files:
        raise RuntimeError(f"No parquet files found in {REPO_ID}")
    if max_shards is None:
        selected = files
    else:
        selected = files[: max(max_shards, min_shards)]
    paths: list[Path] = []
    for filename in selected:
        paths.append(
            Path(
                hf_hub_download(
                    repo_id=REPO_ID,
                    repo_type="dataset",
                    filename=filename,
                    local_dir=str(raw_dir),
                    resume_download=True,
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
        row_index = 0
        for batch in pf.iter_batches(columns=[image_col, label_col, generator_col], batch_size=256):
            images = batch.column(0).to_pylist()
            labels = batch.column(1).to_pylist()
            generators = batch.column(2).to_pylist()
            for image, label, generator in zip(images, labels, generators):
                y_fake = int(label)
                gen_id = int(generator)
                group = ("fake", gen_id) if y_fake == 1 else ("real", 0)
                candidates[group].append(
                    {
                        "image": image,
                        "y_fake": y_fake,
                        "generator_id": gen_id,
                        "source_split": "test",
                        "source_shard": parquet.name,
                        "source_row_index": row_index,
                        "source_id": f"{parquet.stem}_r{row_index:06d}",
                    }
                )
                row_index += 1
    return candidates


def _select(
    candidates: dict[tuple[str, int], list[dict[str, Any]]],
    seed: int,
    per_fake: dict[str, int],
    num_fake_generators: int,
    *,
    allow_shortage: bool = False,
) -> tuple[list[tuple[str, dict[str, Any]]], list[tuple[Any, ...]]]:
    rng = random.Random(seed)
    selected: list[tuple[str, dict[str, Any]]] = []
    shortages: list[tuple[Any, ...]] = []

    for gen_id in range(1, num_fake_generators + 1):
        rows = candidates.get(("fake", gen_id), [])
        rng.shuffle(rows)
        cursor = 0
        for purpose, count in per_fake.items():
            chunk = rows[cursor : cursor + count]
            if len(chunk) < count:
                shortages.append((GEN_NAMES.get(gen_id, gen_id), purpose, len(chunk), count))
            selected.extend((purpose, row) for row in chunk)
            cursor += len(chunk)

    real_rows = candidates.get(("real", 0), [])
    rng.shuffle(real_rows)
    cursor = 0
    for purpose, fake_count in per_fake.items():
        count = fake_count * num_fake_generators
        chunk = real_rows[cursor : cursor + count]
        if len(chunk) < count:
            shortages.append(("Real", purpose, len(chunk), count))
        selected.extend((purpose, row) for row in chunk)
        cursor += len(chunk)

    if shortages and not allow_shortage:
        available = {str(k): len(v) for k, v in candidates.items()}
        raise RuntimeError(f"Insufficient AIGCDetectBenchmark rows: {shortages}; available={available}")
    return selected, shortages


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="/home/bfl-pcf/datasets/aigcdetectbenchmark_lr_sample")
    parser.add_argument("--raw-dir", default="/home/bfl-pcf/datasets/aigcdetectbenchmark_raw")
    parser.add_argument("--seed", type=int, default=20260629)
    parser.add_argument("--train-per-fake", type=int, default=300)
    parser.add_argument("--validation-per-fake", type=int, default=100)
    parser.add_argument("--test-per-fake", type=int, default=100)
    parser.add_argument("--num-fake-generators", type=int, default=17)
    parser.add_argument("--max-shards", type=int, default=None)
    parser.add_argument("--allow-shortage", action="store_true")
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
        "internal_test": args.test_per_fake,
    }
    selected, shortages = _select(
        candidates, args.seed, per_fake, args.num_fake_generators, allow_shortage=args.allow_shortage
    )

    rows = []
    for purpose, row in selected:
        y_fake = int(row["y_fake"])
        gen_id = int(row["generator_id"]) if y_fake == 1 else 0
        generator = GEN_NAMES.get(gen_id, f"generator_{gen_id}")
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
    fake_per_gen = args.train_per_fake + args.validation_per_fake + args.test_per_fake
    summary = {
        "dataset": DATASET,
        "repo_id": REPO_ID,
        "raw_parquets": [str(p) for p in parquets],
        "rows": len(rows),
        "fake_per_generator": fake_per_gen,
        "counts_by_purpose_label": {
            f"{purpose}:{label}": count
            for (purpose, label), count in Counter((r["purpose"], r["label"]) for r in rows).items()
        },
        "counts_by_generator_fake": dict(Counter(r["generator"] for r in rows if r["label"] == "fake")),
        "shortages": [
            {"generator": s[0], "purpose": s[1], "available": s[2], "requested": s[3]} for s in shortages
        ],
    }
    write_json(out_dir / "summary.json", summary)

    summary_txt = out_dir / "summary.txt"
    lines = [
        f"seed={args.seed}",
        f"raw_shards={len(parquets)}",
        f"total_selected={len(rows)}",
        f"fake_targets={per_fake}",
        f"real_targets={{k: v * {args.num_fake_generators} for k, v in per_fake.items()}}",
    ]
    for (purpose, generator, label), count in sorted(
        Counter((r["purpose"], r["generator"], r["label"]) for r in rows).items()
    ):
        lines.append(f"{purpose},{generator},{label},{count}")
    summary_txt.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {len(rows)} rows to {out_dir / 'manifest.csv'}")


if __name__ == "__main__":
    main()
