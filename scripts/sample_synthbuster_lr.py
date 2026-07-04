#!/usr/bin/env python3
"""Sample Synthbuster for out-of-domain LR evaluation."""

from __future__ import annotations

import argparse
import csv
import hashlib
import random
import shutil
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
import requests

from lr_dataset_utils import (
    image_suffix,
    iter_image_files,
    materialize_bytes,
    materialize_file,
    reset_dir,
    safe_name,
    write_json,
    write_manifest,
)

DATASET = "Synthbuster"
SYNTHBUSTER_URL = "https://zenodo.org/records/10066460/files/synthbuster.zip?download=1"


def _download(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        try:
            with zipfile.ZipFile(dest) as zf:
                if zf.testzip() is None:
                    return dest
        except zipfile.BadZipFile:
            pass
    existing = dest.stat().st_size if dest.exists() else 0
    headers = {"Range": f"bytes={existing}-"} if existing else {}
    mode = "ab" if existing else "wb"
    if existing:
        print(f"Resuming {url} -> {dest} at byte {existing}", flush=True)
    else:
        print(f"Downloading {url} -> {dest}", flush=True)
    with requests.get(url, headers=headers, stream=True, timeout=60) as response:
        if existing and response.status_code == 200:
            mode = "wb"
        response.raise_for_status()
        with dest.open(mode) as fh:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    fh.write(chunk)
    return dest


def _extract(zip_path: Path, extract_dir: Path) -> None:
    marker = extract_dir / ".extracted"
    if marker.exists():
        return
    extract_dir.mkdir(parents=True, exist_ok=True)
    print(f"Extracting {zip_path}", flush=True)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(extract_dir)
    marker.write_text("ok\n", encoding="utf-8")


def _infer_generator(path: Path) -> str:
    parts = [p.lower() for p in path.parts]
    names = {
        "dalle2": "DALL-E_2",
        "dalle3": "DALL-E_3",
        "dall-e-2": "DALL-E_2",
        "dall-e-3": "DALL-E_3",
        "firefly": "Adobe_Firefly",
        "glide": "GLIDE",
        "midjourney": "Midjourney_v5",
        "stable-diffusion-1-3": "Stable_Diffusion_1.3",
        "stable-diffusion-1-4": "Stable_Diffusion_1.4",
        "stable-diffusion-2": "Stable_Diffusion_2",
        "stable-diffusion-xl": "Stable_Diffusion_XL",
        "sdxl": "Stable_Diffusion_XL",
    }
    joined = "/".join(parts)
    for token, name in names.items():
        if token in joined:
            return name
    parent = path.parent.name
    return safe_name(parent)


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


def _excluded_sha256(manifest_paths: list[Path]) -> set[str]:
    excluded: set[str] = set()
    for manifest in manifest_paths:
        if not manifest.is_file():
            continue
        with manifest.open(encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                digest = (row.get("sha256") or "").strip()
                if digest:
                    excluded.add(digest)
    return excluded


def _collect_aigcdetect_reals(
    raw_dir: Path,
    *,
    count: int,
    seed: int,
    excluded_sha256: set[str],
) -> list[dict[str, Any]]:
    """Collect distinct real images from AIGCDetectBenchmark parquet shards."""
    rng = random.Random(seed)
    candidates: list[dict[str, Any]] = []
    parquets = sorted((raw_dir / "data").glob("*.parquet"))
    if not parquets:
        raise RuntimeError(f"No AIGCDetect parquet shards under {raw_dir / 'data'}")

    for parquet in parquets:
        pf = pq.ParquetFile(parquet)
        names = pf.schema_arrow.names
        image_col = _column_name(names, ("image", "Image", "img"))
        label_col = _column_name(names, ("Label_A", "label", "Label", "binary_label"))
        row_index = 0
        for batch in pf.iter_batches(columns=[image_col, label_col], batch_size=256):
            images = batch.column(0).to_pylist()
            labels = batch.column(1).to_pylist()
            for image, label in zip(images, labels):
                if int(label) != 0:
                    row_index += 1
                    continue
                candidates.append(
                    {
                        "image": image,
                        "source_split": "aigcdetect_test",
                        "source_shard": parquet.name,
                        "source_id": f"{parquet.stem}_r{row_index:06d}",
                    }
                )
                row_index += 1

    rng.shuffle(candidates)
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in candidates:
        if len(selected) >= count:
            break
        data, source_path = _image_bytes(row["image"])
        digest = hashlib.sha256(data).hexdigest()
        if digest in excluded_sha256 or digest in seen:
            continue
        seen.add(digest)
        row["data"] = data
        row["source_path"] = source_path
        row["sha256"] = digest
        selected.append(row)

    if len(selected) < count:
        raise RuntimeError(
            f"Insufficient distinct AIGCDetect real images: need {count}, got {len(selected)} "
            f"(candidates={len(candidates)}, excluded={len(excluded_sha256)})"
        )
    return selected


def _materialize_bfree_reals(
    *,
    out_dir: Path,
    real_manifest: Path,
    count: int,
    rng: random.Random,
) -> list[dict[str, Any]]:
    real_root = real_manifest.parent
    with real_manifest.open(encoding="utf-8") as fh:
        real_rows = [row for row in csv.DictReader(fh) if row.get("label") == "real"]
    rng.shuffle(real_rows)
    rows: list[dict[str, Any]] = []
    for row in real_rows[:count]:
        source = real_root / row["dest_relative"]
        rows.append(
            materialize_file(
                out_dir=out_dir,
                purpose="out_domain_test",
                dataset=DATASET,
                generator="RAISE",
                generator_id=0,
                label="real",
                y_fake=0,
                source_split="raise_reused_from_bfree_extended",
                source_id=safe_name(source.stem),
                source_path=source,
            )
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="/home/bfl-pcf/datasets/synthbuster_lr_sample")
    parser.add_argument("--raw-dir", default="/home/bfl-pcf/datasets/synthbuster_raw")
    parser.add_argument(
        "--real-source",
        choices=("aigcdetect", "bfree_raise"),
        default="aigcdetect",
        help="Source for real images. Default aigcdetect keeps Synthbuster disjoint from BFree RAISE.",
    )
    parser.add_argument(
        "--aigcdetect-raw-dir",
        default="/home/bfl-pcf/datasets/aigcdetectbenchmark_raw",
    )
    parser.add_argument(
        "--exclude-manifest",
        action="append",
        default=["/home/bfl-pcf/datasets/bfree_extended_lr_sample/manifest.csv"],
        help="Manifest CSVs whose sha256 values must not be reused as Synthbuster reals.",
    )
    parser.add_argument(
        "--real-manifest",
        default="/home/bfl-pcf/datasets/bfree_extended_lr_sample/manifest.csv",
        help="Only used when --real-source=bfree_raise.",
    )
    parser.add_argument("--seed", type=int, default=20260629)
    parser.add_argument("--per-fake", type=int, default=150)
    parser.add_argument("--per-real", type=int, default=4500)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--drop-extracted", action="store_true")
    args = parser.parse_args()

    out_dir = Path(args.out)
    raw_dir = Path(args.raw_dir)
    reset_dir(out_dir, args.force)
    raw_dir.mkdir(parents=True, exist_ok=True)

    archive = _download(SYNTHBUSTER_URL, raw_dir / "synthbuster.zip")
    extract_dir = raw_dir / "synthbuster_extracted"
    _extract(archive, extract_dir)

    fake_by_gen: dict[str, list[Path]] = defaultdict(list)
    for image in iter_image_files(extract_dir):
        fake_by_gen[_infer_generator(image)].append(image)

    rng = random.Random(args.seed)
    rows: list[dict[str, Any]] = []
    for generator, files in sorted(fake_by_gen.items()):
        rng.shuffle(files)
        for path in files[: args.per_fake]:
            rows.append(
                materialize_file(
                    out_dir=out_dir,
                    purpose="out_domain_test",
                    dataset=DATASET,
                    generator=generator,
                    generator_id=generator,
                    label="fake",
                    y_fake=1,
                    source_split="synthbuster",
                    source_id=safe_name(path.stem),
                    source_path=path,
                )
            )

    excluded = _excluded_sha256([Path(p) for p in args.exclude_manifest])
    real_source = args.real_source
    real_copied = 0
    if real_source == "aigcdetect":
        print(
            f"Sampling {args.per_real} distinct reals from AIGCDetect "
            f"(excluding {len(excluded)} sha256 from other manifests)",
            flush=True,
        )
        real_candidates = _collect_aigcdetect_reals(
            Path(args.aigcdetect_raw_dir),
            count=args.per_real,
            seed=args.seed + 17,
            excluded_sha256=excluded,
        )
        for row in real_candidates:
            rows.append(
                materialize_bytes(
                    out_dir=out_dir,
                    purpose="out_domain_test",
                    dataset=DATASET,
                    generator="RAISE",
                    generator_id=0,
                    label="real",
                    y_fake=0,
                    source_split=row["source_split"],
                    source_id=row["source_id"],
                    source_path=row["source_path"],
                    data=row["data"],
                    suffix=image_suffix(row["source_path"]),
                )
            )
        real_copied = len(real_candidates)
    else:
        real_manifest = Path(args.real_manifest)
        if real_manifest.exists():
            real_rows = _materialize_bfree_reals(
                out_dir=out_dir,
                real_manifest=real_manifest,
                count=args.per_real,
                rng=rng,
            )
            rows.extend(real_rows)
            real_copied = len(real_rows)

    write_manifest(out_dir / "manifest.csv", rows)
    write_json(
        out_dir / "summary.json",
        {
            "dataset": DATASET,
            "rows": len(rows),
            "real_rows_reused": real_copied,
            "real_source": real_source,
            "excluded_sha256_count": len(excluded),
            "counts_by_label": dict(Counter(r["label"] for r in rows)),
            "counts_by_generator": dict(Counter(r["generator"] for r in rows)),
            "source_url": SYNTHBUSTER_URL,
        },
    )
    if args.drop_extracted:
        shutil.rmtree(extract_dir, ignore_errors=True)
    print(f"Wrote {len(rows)} rows to {out_dir / 'manifest.csv'}")


if __name__ == "__main__":
    main()
