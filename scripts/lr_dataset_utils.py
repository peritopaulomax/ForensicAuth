#!/usr/bin/env python3
"""Shared helpers for LR calibration dataset scripts."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any, Iterable

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}


def safe_name(value: Any) -> str:
    text = str(value).strip()
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", text).strip("_") or "unknown"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def reset_dir(path: Path, force: bool) -> None:
    if path.exists() and force:
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def image_suffix(path_value: str | None, default: str = ".jpg") -> str:
    suffix = Path(str(path_value or "")).suffix.lower()
    return suffix if suffix in IMAGE_EXTENSIONS else default


def iter_image_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
            yield path


def write_manifest(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "purpose",
        "dataset",
        "generator",
        "generator_id",
        "label",
        "y_fake",
        "source_split",
        "source_id",
        "source_path",
        "dest_relative",
        "sha256",
        "bytes",
        "augmentation",
        "augmentation_params",
        "source_sha256",
    ]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")


def materialize_bytes(
    *,
    out_dir: Path,
    purpose: str,
    dataset: str,
    generator: str,
    generator_id: str | int,
    label: str,
    y_fake: int,
    source_split: str,
    source_id: str,
    source_path: str,
    data: bytes,
    suffix: str,
) -> dict[str, Any]:
    digest = sha256_bytes(data)
    filename = f"{safe_name(source_id)}__{digest[:12]}{suffix}"
    dest_rel = Path(purpose) / safe_name(generator) / safe_name(label) / filename
    dest = out_dir / dest_rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return {
        "purpose": purpose,
        "dataset": dataset,
        "generator": generator,
        "generator_id": generator_id,
        "label": label,
        "y_fake": y_fake,
        "source_split": source_split,
        "source_id": source_id,
        "source_path": source_path,
        "dest_relative": dest_rel.as_posix(),
        "sha256": digest,
        "bytes": len(data),
    }


def materialize_file(
    *,
    out_dir: Path,
    purpose: str,
    dataset: str,
    generator: str,
    generator_id: str | int,
    label: str,
    y_fake: int,
    source_split: str,
    source_id: str,
    source_path: Path,
) -> dict[str, Any]:
    data = source_path.read_bytes()
    return materialize_bytes(
        out_dir=out_dir,
        purpose=purpose,
        dataset=dataset,
        generator=generator,
        generator_id=generator_id,
        label=label,
        y_fake=y_fake,
        source_split=source_split,
        source_id=source_id,
        source_path=str(source_path),
        data=data,
        suffix=image_suffix(source_path.name),
    )
