#!/usr/bin/env python3
"""Sample GRIP B-Free extended Synthbuster dataset for LR tests."""

from __future__ import annotations

import argparse
import random
import shutil
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

import requests
from lr_dataset_utils import iter_image_files, materialize_file, reset_dir, safe_name, write_json, write_manifest

DATASET = "BFree_extended_synthbuster"
BASE_URL = "https://www.grip.unina.it/download/prog/B-Free/extended_synthbuster"
ARCHIVES = {
    "real_RAISE_1k.zip": f"{BASE_URL}/real_RAISE_1k.zip",
    "sd3_flux.zip": f"{BASE_URL}/sd3_flux.zip",
    "latent-diffusion.zip": f"{BASE_URL}/latent-diffusion.zip",
}


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
            # Server ignored Range; restart to avoid corrupt concatenation.
            existing = 0
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
    text = path.as_posix().lower()
    if "flux" in text:
        return "FLUX"
    if "sd3" in text or "stable_diffusion_3" in text or "stable-diffusion-3" in text:
        return "Stable_Diffusion_3.5"
    if "latent" in text:
        return "latent-diffusion"
    return "unknown_fake"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="/home/bfl-pcf/datasets/bfree_extended_lr_sample")
    parser.add_argument("--raw-dir", default="/home/bfl-pcf/datasets/bfree_extended_raw")
    parser.add_argument("--seed", type=int, default=20260629)
    parser.add_argument("--per-fake", type=int, default=300)
    parser.add_argument("--per-real", type=int, default=600)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--drop-extracted", action="store_true")
    args = parser.parse_args()

    out_dir = Path(args.out)
    raw_dir = Path(args.raw_dir)
    reset_dir(out_dir, args.force)
    raw_dir.mkdir(parents=True, exist_ok=True)

    for name, url in ARCHIVES.items():
        archive = _download(url, raw_dir / name)
        _extract(archive, raw_dir / f"{archive.stem}_extracted")

    real_files = list(iter_image_files(raw_dir / "real_RAISE_1k_extracted"))
    fake_by_gen: dict[str, list[Path]] = defaultdict(list)
    for root_name in ("sd3_flux_extracted", "latent-diffusion_extracted"):
        for image in iter_image_files(raw_dir / root_name):
            fake_by_gen[_infer_generator(image)].append(image)

    rng = random.Random(args.seed)
    rows = []
    rng.shuffle(real_files)
    for path in real_files[: args.per_real]:
        rows.append(
            materialize_file(
                out_dir=out_dir,
                purpose="out_domain_test",
                dataset=DATASET,
                generator="RAISE",
                generator_id=0,
                label="real",
                y_fake=0,
                source_split="extended_synthbuster",
                source_id=safe_name(path.stem),
                source_path=path,
            )
        )
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
                    source_split="extended_synthbuster",
                    source_id=safe_name(path.stem),
                    source_path=path,
                )
            )

    write_manifest(out_dir / "manifest.csv", rows)
    write_json(
        out_dir / "summary.json",
        {
            "dataset": DATASET,
            "rows": len(rows),
            "counts_by_label": dict(Counter(r["label"] for r in rows)),
            "counts_by_generator": dict(Counter(r["generator"] for r in rows)),
            "archives": ARCHIVES,
        },
    )
    if args.drop_extracted:
        for path in raw_dir.glob("*_extracted"):
            shutil.rmtree(path, ignore_errors=True)
    print(f"Wrote {len(rows)} rows to {out_dir / 'manifest.csv'}")


if __name__ == "__main__":
    main()
