#!/usr/bin/env python3
"""Sample selected OpenSDI test subsets for hard out-of-domain LR evaluation."""

from __future__ import annotations

import argparse
import random
from collections import Counter
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
from huggingface_hub import HfApi, hf_hub_download

from lr_dataset_utils import image_suffix, materialize_bytes, reset_dir, write_json, write_manifest

REPO_ID = "nebula/OpenSDI_test"
DATASET = "OpenSDI_test"


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


def _find_column(names: list[str], candidates: tuple[str, ...]) -> str | None:
    lowered = {name.lower(): name for name in names}
    for candidate in candidates:
        if candidate.lower() in lowered:
            return lowered[candidate.lower()]
    return None


def _download_subset(raw_dir: Path, subset: str, max_shards: int | None) -> list[Path]:
    api = HfApi()
    files = sorted(
        f
        for f in api.list_repo_files(repo_id=REPO_ID, repo_type="dataset")
        if f.endswith(".parquet") and f"/{subset}-" in f
    )
    if not files:
        files = sorted(
            f
            for f in api.list_repo_files(repo_id=REPO_ID, repo_type="dataset")
            if f.endswith(".parquet") and Path(f).name.startswith(f"{subset}-")
        )
    if not files:
        raise RuntimeError(f"No parquet files found for OpenSDI subset {subset}")
    selected = files if max_shards is None else files[:max_shards]
    return [
        Path(hf_hub_download(repo_id=REPO_ID, repo_type="dataset", filename=filename, local_dir=str(raw_dir)))
        for filename in selected
    ]


def _collect(parquets: list[Path], subset: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    fake_rows: list[dict[str, Any]] = []
    real_rows: list[dict[str, Any]] = []
    for parquet in parquets:
        pf = pq.ParquetFile(parquet)
        names = pf.schema_arrow.names
        image_col = _find_column(names, ("image", "Image", "img"))
        label_col = _find_column(names, ("label", "Label", "y", "target"))
        if image_col is None:
            raise RuntimeError(f"OpenSDI parquet has no image column: {names}")
        columns = [image_col] + ([label_col] if label_col else [])
        for batch in pf.iter_batches(columns=columns, batch_size=256):
            images = batch.column(0).to_pylist()
            labels = batch.column(1).to_pylist() if label_col else [None] * len(images)
            for idx, (image, label_value) in enumerate(zip(images, labels)):
                if label_value is None:
                    text = str(image).lower()
                    y_fake = 0 if "real" in text else 1
                else:
                    y_fake = int(label_value)
                row = {
                    "image": image,
                    "y_fake": y_fake,
                    "source_split": subset,
                    "source_id": f"{parquet.stem}_r{idx:06d}",
                }
                (fake_rows if y_fake else real_rows).append(row)
    return real_rows, fake_rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="/home/bfl-pcf/datasets/opensdi_lr_sample")
    parser.add_argument("--raw-dir", default="/home/bfl-pcf/datasets/opensdi_raw")
    parser.add_argument("--subsets", default="flux,sd3")
    parser.add_argument("--seed", type=int, default=20260629)
    parser.add_argument("--per-class", type=int, default=300)
    parser.add_argument("--max-shards-per-subset", type=int, default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    out_dir = Path(args.out)
    raw_dir = Path(args.raw_dir)
    reset_dir(out_dir, args.force)
    raw_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)

    rows = []
    for subset in [s.strip() for s in args.subsets.split(",") if s.strip()]:
        parquets = _download_subset(raw_dir, subset, args.max_shards_per_subset)
        real_rows, fake_rows = _collect(parquets, subset)
        rng.shuffle(real_rows)
        rng.shuffle(fake_rows)
        for label, selected in (("real", real_rows[: args.per_class]), ("fake", fake_rows[: args.per_class])):
            for row in selected:
                data, source_path = _image_bytes(row["image"])
                y_fake = 1 if label == "fake" else 0
                rows.append(
                    materialize_bytes(
                        out_dir=out_dir,
                        purpose="out_domain_test",
                        dataset=DATASET,
                        generator=subset if y_fake else "OpenSDI_real",
                        generator_id=subset if y_fake else 0,
                        label=label,
                        y_fake=y_fake,
                        source_split=subset,
                        source_id=row["source_id"],
                        source_path=source_path,
                        data=data,
                        suffix=image_suffix(source_path),
                    )
                )

    write_manifest(out_dir / "manifest.csv", rows)
    write_json(
        out_dir / "summary.json",
        {
            "dataset": DATASET,
            "repo_id": REPO_ID,
            "rows": len(rows),
            "counts_by_label": dict(Counter(r["label"] for r in rows)),
            "counts_by_generator": dict(Counter(r["generator"] for r in rows)),
        },
    )
    print(f"Wrote {len(rows)} rows to {out_dir / 'manifest.csv'}")


if __name__ == "__main__":
    main()
