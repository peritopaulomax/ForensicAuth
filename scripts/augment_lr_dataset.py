#!/usr/bin/env python3
"""Generate forensically-controlled augmented variants of an LR sample dataset.

Each source image listed in a manifest CSV is used to produce deterministic
variations that mimic common real-world processing:

- jpeg_85       : re-compressed as JPEG quality 85
- webp_80       : re-compressed as WebP quality 80
- crop_upscale  : central crop to 80% of area (~89.4% of side), then resized back
- resize_down_50: resized to 50% of original dimensions

A new manifest is written with the same columns as the source plus
`augmentation` and `augmentation_params`.  SHA-256 of the source file and of
each generated file are recorded to preserve the digital chain of custody.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
from pathlib import Path
from typing import Any

from PIL import Image

from lr_dataset_utils import (
    IMAGE_EXTENSIONS,
    iter_image_files,
    materialize_bytes,
    reset_dir,
    safe_name,
    sha256_file,
    write_json,
    write_manifest,
)


AUGMENTATIONS = ("jpeg_85", "webp_80", "crop_upscale", "resize_down_50")


def _crop_upscale_size(width: int, height: int, area_ratio: float = 0.8) -> tuple[int, int]:
    """Return (crop_w, crop_h) such that crop area == area_ratio * original area."""
    side_ratio = math.sqrt(area_ratio)
    crop_w = max(1, int(round(width * side_ratio)))
    crop_h = max(1, int(round(height * side_ratio)))
    return crop_w, crop_h


def _centre_crop_box(width: int, height: int, crop_w: int, crop_h: int) -> tuple[int, int, int, int]:
    left = (width - crop_w) // 2
    top = (height - crop_h) // 2
    return left, top, left + crop_w, top + crop_h


def _variant_bytes(image: Image.Image, aug: str, source_ext: str) -> tuple[bytes, str, dict[str, Any]]:
    """Return (file_bytes, suffix, params_dict) for a single augmentation."""
    rgb = image.convert("RGB")
    w, h = rgb.size

    if aug == "jpeg_85":
        params = {"format": "JPEG", "quality": 85, "subsampling": "keep"}
        out_format = "JPEG"
        suffix = ".jpg"
        buf = _save_to_buffer(rgb, out_format, quality=85)

    elif aug == "webp_80":
        params = {"format": "WebP", "quality": 80, "method": 6}
        out_format = "WEBP"
        suffix = ".webp"
        buf = _save_to_buffer(rgb, out_format, quality=80, method=6)

    elif aug == "crop_upscale":
        area_ratio = 0.8
        crop_w, crop_h = _crop_upscale_size(w, h, area_ratio)
        box = _centre_crop_box(w, h, crop_w, crop_h)
        cropped = rgb.crop(box)
        resized = cropped.resize((w, h), Image.Resampling.LANCZOS)
        params = {
            "area_ratio": area_ratio,
            "side_ratio": round(math.sqrt(area_ratio), 6),
            "crop_box": box,
            "original_size": [w, h],
            "output_size": [w, h],
            "resample": "LANCZOS",
        }
        out_format = "PNG" if source_ext in {".png", ".webp"} else "JPEG"
        suffix = ".png" if out_format == "PNG" else ".jpg"
        if out_format == "PNG":
            buf = _save_to_buffer(resized, out_format)
        else:
            buf = _save_to_buffer(resized, out_format, quality=95)

    elif aug == "resize_down_50":
        new_w = max(1, w // 2)
        new_h = max(1, h // 2)
        resized = rgb.resize((new_w, new_h), Image.Resampling.LANCZOS)
        params = {
            "scale": 0.5,
            "original_size": [w, h],
            "output_size": [new_w, new_h],
            "resample": "LANCZOS",
        }
        out_format = "PNG" if source_ext in {".png", ".webp"} else "JPEG"
        suffix = ".png" if out_format == "PNG" else ".jpg"
        if out_format == "PNG":
            buf = _save_to_buffer(resized, out_format)
        else:
            buf = _save_to_buffer(resized, out_format, quality=95)

    else:
        raise ValueError(f"Unknown augmentation: {aug}")

    return buf, suffix, params


def _save_to_buffer(image: Image.Image, fmt: str, **kwargs: Any) -> bytes:
    bio = __import__("io").BytesIO()
    image.save(bio, format=fmt, **kwargs)
    return bio.getvalue()


def _read_manifest(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _output_relative(
    purpose: str,
    generator: str,
    label: str,
    source_id: str,
    aug: str,
    suffix: str,
    digest: str,
) -> Path:
    return Path(
        purpose,
        safe_name(generator),
        safe_name(label),
        "augmented",
        safe_name(aug),
        f"{safe_name(source_id)}__{aug}__{digest[:12]}{suffix}",
    )


def augment_manifest(
    *,
    manifest_path: Path,
    out_dir: Path,
    augmentations: tuple[str, ...] = AUGMENTATIONS,
    force: bool = False,
) -> dict[str, Any]:
    """Generate augmented images and a new manifest for every row of ``manifest_path``."""
    reset_dir(out_dir, force=force)

    rows = _read_manifest(manifest_path)
    manifest_root = manifest_path.parent
    output_rows: list[dict[str, Any]] = []

    stats: dict[str, Any] = {
        "source_manifest": str(manifest_path),
        "out_dir": str(out_dir),
        "source_rows": len(rows),
        "augmentations": list(augmentations),
        "errors": 0,
        "generated": {aug: 0 for aug in augmentations},
    }

    for idx, row in enumerate(rows, start=1):
        source_rel = row.get("dest_relative") or ""
        source_path = manifest_root / source_rel if source_rel else Path(row.get("source_path", ""))
        source_id = row.get("source_id", f"row_{idx}")
        purpose = row.get("purpose", "augmented")
        dataset = row.get("dataset", "Unknown")
        generator = row.get("generator", "unknown")
        generator_id = row.get("generator_id", "")
        label = row.get("label", "")
        y_fake = int(row.get("y_fake", "1" if label == "fake" else "0"))
        source_split = row.get("source_split", "")

        if not source_path.is_file():
            stats["errors"] += 1
            print(f"[WARN] Missing source file: {source_path}")
            continue

        source_sha256 = sha256_file(source_path)
        source_ext = Path(source_path.name).suffix.lower()
        if source_ext not in IMAGE_EXTENSIONS:
            source_ext = ".jpg"

        try:
            with Image.open(source_path) as image:
                image.load()
                base_image = image.copy()
        except Exception as exc:
            stats["errors"] += 1
            print(f"[WARN] Cannot open {source_path}: {exc}")
            continue

        for aug in augmentations:
            try:
                data, suffix, params = _variant_bytes(base_image, aug, source_ext)
                digest = __import__("hashlib").sha256(data).hexdigest()
                dest_rel = _output_relative(purpose, generator, label, source_id, aug, suffix, digest)
                dest = out_dir / dest_rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)

                output_rows.append({
                    "purpose": purpose,
                    "dataset": dataset,
                    "generator": generator,
                    "generator_id": generator_id,
                    "label": label,
                    "y_fake": y_fake,
                    "source_split": source_split,
                    "source_id": f"{source_id}_{aug}",
                    "source_path": str(source_path),
                    "dest_relative": dest_rel.as_posix(),
                    "sha256": digest,
                    "bytes": len(data),
                    "augmentation": aug,
                    "augmentation_params": json.dumps(params, sort_keys=True, ensure_ascii=False),
                    "source_sha256": source_sha256,
                })
                stats["generated"][aug] += 1
            except Exception as exc:
                stats["errors"] += 1
                print(f"[WARN] Augmentation {aug} failed for {source_path}: {exc}")

        if idx % 100 == 0:
            print(f"Processed {idx}/{len(rows)} source rows", flush=True)

    write_manifest(out_dir / "manifest.csv", output_rows)
    write_json(out_dir / "summary.json", stats)
    print(json.dumps(stats, indent=2, sort_keys=True, ensure_ascii=False))
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate augmented variants of an LR sample dataset.")
    parser.add_argument("--manifest", required=True, type=Path, help="Source manifest CSV.")
    parser.add_argument("--out-dir", required=True, type=Path, help="Output directory for augmented images + manifest.")
    parser.add_argument("--augmentations", default=",".join(AUGMENTATIONS), help="Comma-separated augmentation names.")
    parser.add_argument("--force", action="store_true", help="Erase out-dir if it already exists.")
    args = parser.parse_args()

    augmentations = tuple(item.strip() for item in args.augmentations.split(",") if item.strip())
    for aug in augmentations:
        if aug not in AUGMENTATIONS:
            raise ValueError(f"Unknown augmentation '{aug}'. Supported: {AUGMENTATIONS}")

    augment_manifest(
        manifest_path=args.manifest,
        out_dir=args.out_dir,
        augmentations=augmentations,
        force=args.force,
    )


if __name__ == "__main__":
    main()
