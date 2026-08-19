#!/usr/bin/env python3
"""Ingest a synthetic-image reference base into ForensicAuth.

Protocol CSV (required columns, header required)::

    image_path,base_id,subgroup,y_fake

Optional columns::

    source_id,purpose

``y_fake`` accepts ``0``/``1``, ``real``/``fake``, ``nature``/``ai``.

Pipeline order (canonical paths first, then GPU features)::

    1. Validate protocol (single ``base_id`` per run)
    2. Materialize originals → ``va-reference_build/synthetic_image/originals/<base_id>/``
    3. Generate augs → ``.../augmented/<base_id>/`` (jpeg_85, webp_80, crop_upscale, resize_down_50)
    4. Score + embed (ForensicAuth ``predict_ensemble``) → ``reference_data/.../features/``
    5. Optionally register catalog (``macros.yaml``, ``bases.json``)



Example::

    conda activate va-suite
    cd "/home/bfl-pcf/VA Suite"
    PYTHONPATH=src/backend python scripts/ingest_synthetic_image_reference.py \\
        --protocol path/to/protocol.csv \\
        --dataset-id MyNewBench \\
        --base-group MyNewBench \\
        --macro-id other_neural \\
        --register-catalog
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

# ---------------------------------------------------------------------------
# Repo bootstrap (script lives in scripts/)
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "src" / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from PIL import Image  # noqa: E402

AUGMENTATION_NAMES: tuple[str, ...] = ("jpeg_85", "webp_80", "crop_upscale", "resize_down_50")
ORIGINAL_TAG = "original"

DETECTORS: tuple[str, ...] = (
    "ai_image_detector_deploy",
    "sdxl_flux_detector_v1_1",
    "bfree",
    "corvi2023",
    "safe",
)

PROTOCOL_REQUIRED = ("image_path", "base_id", "subgroup", "y_fake")

SCORE_FIELDNAMES: list[str] = [
    "dataset",
    "purpose",
    "generator",
    "generator_id",
    "label",
    "y_fake",
    "source_split",
    "source_id",
    "dest_relative",
    "image_path",
    "image_sha256",
    "error",
    "elapsed_seconds",
    "ai_image_detector_deploy_fake_prob",
    "ai_image_detector_deploy_real_prob",
    "ai_image_detector_deploy_raw_score",
    "ai_image_detector_deploy_decision",
    "ai_image_detector_deploy_device",
    "sdxl_flux_detector_v1_1_fake_prob",
    "sdxl_flux_detector_v1_1_real_prob",
    "sdxl_flux_detector_v1_1_raw_score",
    "sdxl_flux_detector_v1_1_decision",
    "sdxl_flux_detector_v1_1_device",
    "bfree_fake_prob",
    "bfree_real_prob",
    "bfree_raw_score",
    "bfree_decision",
    "bfree_device",
    "corvi2023_fake_prob",
    "corvi2023_real_prob",
    "corvi2023_raw_score",
    "corvi2023_decision",
    "corvi2023_device",
    "safe_fake_prob",
    "safe_real_prob",
    "safe_raw_score",
    "safe_decision",
    "safe_device",
    "safe_error",
    "safe_elapsed_seconds",
]

SCORE_AUG_FIELDNAMES = SCORE_FIELDNAMES + ["augmentation"]

REP_FIELDNAMES: list[str] = [
    "ai_image_detector_deploy_decision",
    "ai_image_detector_deploy_embedding_dim",
    "ai_image_detector_deploy_embedding_path",
    "ai_image_detector_deploy_fake_prob",
    "ai_image_detector_deploy_raw_score",
    "ai_image_detector_deploy_real_prob",
    "augmentation",
    "bfree_decision",
    "bfree_embedding_dim",
    "bfree_embedding_path",
    "bfree_fake_prob",
    "bfree_raw_score",
    "bfree_real_prob",
    "corvi2023_decision",
    "corvi2023_embedding_dim",
    "corvi2023_embedding_path",
    "corvi2023_fake_prob",
    "corvi2023_raw_score",
    "corvi2023_real_prob",
    "dataset",
    "error",
    "generator",
    "image_path",
    "label",
    "purpose",
    "safe_decision",
    "safe_embedding_dim",
    "safe_embedding_path",
    "safe_fake_prob",
    "safe_raw_score",
    "safe_real_prob",
    "sample_id",
    "sdxl_flux_detector_v1_1_decision",
    "sdxl_flux_detector_v1_1_embedding_dim",
    "sdxl_flux_detector_v1_1_embedding_path",
    "sdxl_flux_detector_v1_1_fake_prob",
    "sdxl_flux_detector_v1_1_raw_score",
    "sdxl_flux_detector_v1_1_real_prob",
    "source_id",
    "y_fake",
]

MANIFEST_FIELDNAMES: list[str] = [
    "base_id",
    "dataset_id",
    "dataset",
    "purpose",
    "generator",
    "generator_id",
    "label",
    "y_fake",
    "source_split",
    "source_id",
    "source_path",
    "augmentation",
    "augmentation_params",
    "local_relpath",
    "sha256",
    "bytes",
    "source_sha256",
]


# ---------------------------------------------------------------------------
# Protocol / helpers
# ---------------------------------------------------------------------------


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_name(text: str, max_len: int = 120) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "._-+" else "_" for ch in str(text).strip())
    cleaned = cleaned.strip("._") or "item"
    return cleaned[:max_len]


def parse_y_fake(raw: Any) -> int:
    text = str(raw).strip().lower()
    if text in {"1", "true", "fake", "synthetic", "ai", "spoof"}:
        return 1
    if text in {"0", "false", "real", "nature", "bonafide", "authentic"}:
        return 0
    raise ValueError(f"y_fake invalido: {raw!r} (use 0/1, real/fake, nature/ai)")


def label_for_y_fake(y_fake: int) -> str:
    return "ai" if int(y_fake) == 1 else "nature"


@dataclass(frozen=True)
class ProtocolRow:
    image_path: Path
    base_id: str
    subgroup: str
    y_fake: int
    source_id: str
    purpose: str
    row_index: int


def load_protocol_csv(path: Path, *, media_root: Path | None = None) -> list[ProtocolRow]:
    """Load and validate the ingestion protocol CSV."""
    if not path.is_file():
        raise FileNotFoundError(f"Protocolo nao encontrado: {path}")
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            raise ValueError("Protocolo CSV sem cabecalho")
        fields = {name.strip() for name in reader.fieldnames}
        missing = [col for col in PROTOCOL_REQUIRED if col not in fields]
        if missing:
            raise ValueError(
                "Protocolo CSV precisa das colunas "
                + ", ".join(PROTOCOL_REQUIRED)
                + f". Faltando: {', '.join(missing)}"
            )
        rows: list[ProtocolRow] = []
        for idx, raw in enumerate(reader, start=1):
            image_raw = str(raw.get("image_path") or "").strip()
            if not image_raw:
                raise ValueError(f"Linha {idx}: image_path vazio")
            image_path = Path(image_raw).expanduser()
            if not image_path.is_absolute() and media_root is not None:
                image_path = (media_root / image_path).resolve()
            else:
                image_path = image_path.resolve()
            base_id = safe_name(str(raw.get("base_id") or "").strip().lower().replace("-", "_"))
            subgroup = str(raw.get("subgroup") or "").strip() or "default"
            y_fake = parse_y_fake(raw.get("y_fake"))
            source_id = str(raw.get("source_id") or "").strip() or f"row_{idx}"
            purpose = str(raw.get("purpose") or "").strip() or "calibration_train"
            if not base_id:
                raise ValueError(f"Linha {idx}: base_id vazio")
            rows.append(
                ProtocolRow(
                    image_path=image_path,
                    base_id=base_id,
                    subgroup=subgroup,
                    y_fake=y_fake,
                    source_id=safe_name(source_id),
                    purpose=purpose,
                    row_index=idx,
                )
            )
    if not rows:
        raise ValueError("Protocolo CSV vazio")
    base_ids = {row.base_id for row in rows}
    if len(base_ids) != 1:
        raise ValueError(f"Uma execucao aceita um unico base_id; encontrados: {sorted(base_ids)}")
    missing_files = [str(row.image_path) for row in rows if not row.image_path.is_file()]
    if missing_files:
        preview = ", ".join(missing_files[:5])
        more = f" (+{len(missing_files) - 5} outros)" if len(missing_files) > 5 else ""
        raise FileNotFoundError(f"Imagens ausentes no protocolo: {preview}{more}")
    return rows


# ---------------------------------------------------------------------------
# Augmentations (product names; reimplemented — not imported from ops)
# ---------------------------------------------------------------------------


def _save_to_buffer(image: Image.Image, fmt: str, **kwargs: Any) -> bytes:
    bio = io.BytesIO()
    image.save(bio, format=fmt, **kwargs)
    return bio.getvalue()


def _crop_upscale_size(width: int, height: int, area_ratio: float = 0.8) -> tuple[int, int]:
    side_ratio = math.sqrt(area_ratio)
    return max(1, int(round(width * side_ratio))), max(1, int(round(height * side_ratio)))


def _centre_crop_box(width: int, height: int, crop_w: int, crop_h: int) -> tuple[int, int, int, int]:
    left = (width - crop_w) // 2
    top = (height - crop_h) // 2
    return left, top, left + crop_w, top + crop_h


def make_augmentation(image: Image.Image, aug: str, source_ext: str) -> tuple[bytes, str, dict[str, Any]]:
    """Return (file_bytes, suffix, params) for one product augmentation."""
    rgb = image.convert("RGB")
    w, h = rgb.size
    source_ext = source_ext.lower()

    if aug == "jpeg_85":
        params = {"format": "JPEG", "quality": 85, "subsampling": "keep"}
        return _save_to_buffer(rgb, "JPEG", quality=85), ".jpg", params

    if aug == "webp_80":
        params = {"format": "WebP", "quality": 80, "method": 6}
        return _save_to_buffer(rgb, "WEBP", quality=80, method=6), ".webp", params

    if aug == "crop_upscale":
        area_ratio = 0.8
        crop_w, crop_h = _crop_upscale_size(w, h, area_ratio)
        box = _centre_crop_box(w, h, crop_w, crop_h)
        cropped = rgb.crop(box)
        resized = cropped.resize((w, h), Image.Resampling.LANCZOS)
        params = {
            "area_ratio": area_ratio,
            "side_ratio": round(math.sqrt(area_ratio), 6),
            "crop_box": list(box),
            "original_size": [w, h],
            "output_size": [w, h],
            "resample": "LANCZOS",
        }
        if source_ext in {".png", ".webp"}:
            return _save_to_buffer(resized, "PNG"), ".png", params
        return _save_to_buffer(resized, "JPEG", quality=95), ".jpg", params

    if aug == "resize_down_50":
        new_w = max(1, w // 2)
        new_h = max(1, h // 2)
        resized = rgb.resize((new_w, new_h), Image.Resampling.LANCZOS)
        params = {
            "scale": 0.5,
            "original_size": [w, h],
            "output_size": [new_w, new_h],
            "resample": "LANCZOS",
        }
        if source_ext in {".png", ".webp"}:
            return _save_to_buffer(resized, "PNG"), ".png", params
        return _save_to_buffer(resized, "JPEG", quality=95), ".jpg", params

    raise ValueError(f"Augmentacao desconhecida: {aug}")


# ---------------------------------------------------------------------------
# Materialize + manifests
# ---------------------------------------------------------------------------


@dataclass
class MediaRecord:
    protocol: ProtocolRow
    dataset_id: str
    local_path: Path
    local_relpath: str
    sha256: str
    nbytes: int
    source_sha256: str
    source_path: str
    augmentation: str = ORIGINAL_TAG
    augmentation_params: dict[str, Any] = field(default_factory=dict)

    @property
    def sample_id(self) -> str:
        if self.augmentation == ORIGINAL_TAG:
            return f"{self.dataset_id}__{self.protocol.subgroup}__{self.protocol.source_id}__{ORIGINAL_TAG}"
        return (
            f"{self.dataset_id}__{self.protocol.subgroup}__{self.protocol.source_id}"
            f"__{self.augmentation}"
        )


def _original_dest(
    build_root: Path,
    row: ProtocolRow,
    *,
    digest12: str,
) -> tuple[Path, str]:
    label = label_for_y_fake(row.y_fake)
    filename = f"{digest12}__{safe_name(row.image_path.name)}"
    rel = Path("synthetic_image") / "originals" / row.base_id / row.purpose / row.subgroup / label / filename
    return build_root / rel, str(rel).replace("\\", "/")


def _aug_dest(
    build_root: Path,
    row: ProtocolRow,
    *,
    aug: str,
    digest12: str,
    suffix: str,
) -> tuple[Path, str]:
    label = label_for_y_fake(row.y_fake)
    filename = f"{row.source_id}__{aug}__{digest12}{suffix}"
    rel = (
        Path("synthetic_image")
        / "augmented"
        / row.base_id
        / row.purpose
        / row.subgroup
        / label
        / "augmented"
        / aug
        / filename
    )
    return build_root / rel, str(rel).replace("\\", "/")


def materialize_originals(
    rows: list[ProtocolRow],
    *,
    build_root: Path,
    dataset_id: str,
) -> list[MediaRecord]:
    out: list[MediaRecord] = []
    for row in rows:
        if not row.image_path.is_file():
            raise FileNotFoundError(row.image_path)
        digest = sha256_file(row.image_path)
        dest, rel = _original_dest(build_root, row, digest12=digest[:12])
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.is_file() or sha256_file(dest) != digest:
            shutil.copy2(row.image_path, dest)
        out.append(
            MediaRecord(
                protocol=row,
                dataset_id=dataset_id,
                local_path=dest.resolve(),
                local_relpath=rel,
                sha256=digest,
                nbytes=dest.stat().st_size,
                source_sha256=digest,
                source_path=str(row.image_path),
                augmentation=ORIGINAL_TAG,
            )
        )
    return out


def generate_augmentations(
    originals: list[MediaRecord],
    *,
    build_root: Path,
) -> list[MediaRecord]:
    out: list[MediaRecord] = []
    for record in originals:
        with Image.open(record.local_path) as img:
            image = img.copy()
        source_ext = record.local_path.suffix.lower() or ".jpg"
        for aug in AUGMENTATION_NAMES:
            payload, suffix, params = make_augmentation(image, aug, source_ext)
            digest = sha256_bytes(payload)
            dest, rel = _aug_dest(
                build_root,
                record.protocol,
                aug=aug,
                digest12=digest[:12],
                suffix=suffix,
            )
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.is_file() or sha256_file(dest) != digest:
                dest.write_bytes(payload)
            out.append(
                MediaRecord(
                    protocol=record.protocol,
                    dataset_id=record.dataset_id,
                    local_path=dest.resolve(),
                    local_relpath=rel,
                    sha256=digest,
                    nbytes=len(payload),
                    source_sha256=record.sha256,
                    source_path=str(record.local_path),
                    augmentation=aug,
                    augmentation_params=params,
                )
            )
    return out


def append_manifest(path: Path, records: Iterable[MediaRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_keys: set[str] = set()
    if path.is_file():
        with path.open("r", encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                key = f"{row.get('local_relpath')}|{row.get('augmentation') or ORIGINAL_TAG}"
                existing_keys.add(key)
    write_header = not path.is_file() or path.stat().st_size == 0
    with path.open("a", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=MANIFEST_FIELDNAMES)
        if write_header:
            writer.writeheader()
        for record in records:
            key = f"{record.local_relpath}|{record.augmentation}"
            if key in existing_keys:
                continue
            writer.writerow(
                {
                    "base_id": record.protocol.base_id,
                    "dataset_id": record.dataset_id,
                    "dataset": record.dataset_id,
                    "purpose": record.protocol.purpose,
                    "generator": record.protocol.subgroup,
                    "generator_id": "",
                    "label": label_for_y_fake(record.protocol.y_fake),
                    "y_fake": int(record.protocol.y_fake),
                    "source_split": "",
                    "source_id": record.protocol.source_id
                    if record.augmentation == ORIGINAL_TAG
                    else f"{record.protocol.source_id}_{record.augmentation}",
                    "source_path": record.source_path,
                    "augmentation": "" if record.augmentation == ORIGINAL_TAG else record.augmentation,
                    "augmentation_params": json.dumps(record.augmentation_params, sort_keys=True)
                    if record.augmentation_params
                    else "",
                    "local_relpath": record.local_relpath,
                    "sha256": record.sha256,
                    "bytes": record.nbytes,
                    "source_sha256": record.source_sha256,
                }
            )
            existing_keys.add(key)


def update_bases_json(
    build_root: Path,
    *,
    base_id: str,
    dataset_id: str,
) -> None:
    path = build_root / "bases.json"
    doc: dict[str, Any]
    if path.is_file():
        doc = json.loads(path.read_text(encoding="utf-8"))
    else:
        doc = {"root": str(build_root), "audio_spoofing": {}, "synthetic_image": {}}
    syn = doc.setdefault("synthetic_image", {})
    bases = list(syn.get("bases") or [])
    if base_id not in bases:
        bases.append(base_id)
        bases.sort()
    syn["bases"] = bases
    mapping = dict(syn.get("dataset_id_map") or {})
    mapping[base_id] = dataset_id
    syn["dataset_id_map"] = mapping
    doc["root"] = str(build_root)
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Scoring / embeddings
# ---------------------------------------------------------------------------


def _existing_score_keys(path: Path, *, with_aug: bool) -> set[str]:
    keys: set[str] = set()
    if not path.is_file() or path.stat().st_size == 0:
        return keys
    with path.open("r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            sha = str(row.get("image_sha256") or "")
            if not sha:
                continue
            if with_aug:
                keys.add(f"{sha}|{row.get('augmentation') or ORIGINAL_TAG}")
            else:
                keys.add(sha)
    return keys


def _existing_rep_keys(path: Path) -> set[str]:
    keys: set[str] = set()
    if not path.is_file() or path.stat().st_size == 0:
        return keys
    with path.open("r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            sid = str(row.get("sample_id") or "")
            if sid:
                keys.add(sid)
    return keys


def _append_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.is_file() or path.stat().st_size == 0
    with path.open("a", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def _score_row_from_detector_scores(
    record: MediaRecord,
    detector_scores: dict[str, dict[str, Any]],
    *,
    elapsed: float,
    error: str = "",
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "dataset": record.dataset_id,
        "purpose": record.protocol.purpose,
        "generator": record.protocol.subgroup,
        "generator_id": "",
        "label": label_for_y_fake(record.protocol.y_fake),
        "y_fake": int(record.protocol.y_fake),
        "source_split": "",
        "source_id": record.protocol.source_id
        if record.augmentation == ORIGINAL_TAG
        else f"{record.protocol.source_id}_{record.augmentation}",
        "dest_relative": record.local_relpath,
        "image_path": str(record.local_path),
        "image_sha256": record.sha256,
        "error": error,
        "elapsed_seconds": round(float(elapsed), 6),
        "safe_error": "",
        "safe_elapsed_seconds": "",
    }
    for detector in DETECTORS:
        scores = detector_scores.get(detector) or {}
        row[f"{detector}_fake_prob"] = scores.get("fake_prob", "")
        row[f"{detector}_real_prob"] = scores.get("real_prob", "")
        raw = scores.get("raw_score")
        row[f"{detector}_raw_score"] = "" if raw is None else raw
        row[f"{detector}_decision"] = scores.get("decision", "")
        row[f"{detector}_device"] = scores.get("device", "")
    if record.augmentation != ORIGINAL_TAG:
        row["augmentation"] = record.augmentation
    return row


def _rep_row_from_detector_scores(
    record: MediaRecord,
    detector_scores: dict[str, dict[str, Any]],
    embedding_paths: dict[str, str],
    *,
    error: str = "",
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "augmentation": record.augmentation,
        "dataset": record.dataset_id,
        "error": error,
        "generator": record.protocol.subgroup,
        "image_path": str(record.local_path),
        "label": label_for_y_fake(record.protocol.y_fake),
        "purpose": record.protocol.purpose,
        "sample_id": record.sample_id,
        "source_id": record.protocol.source_id,
        "y_fake": int(record.protocol.y_fake),
    }
    for detector in DETECTORS:
        scores = detector_scores.get(detector) or {}
        emb_path = embedding_paths.get(detector, "")
        dim = scores.get("embedding_dim", "")
        if emb_path and not dim and scores.get("embedding") is not None:
            import numpy as np

            dim = int(np.asarray(scores["embedding"]).size)
        row[f"{detector}_decision"] = scores.get("decision", "")
        row[f"{detector}_embedding_dim"] = dim
        row[f"{detector}_embedding_path"] = emb_path
        row[f"{detector}_fake_prob"] = scores.get("fake_prob", "")
        raw = scores.get("raw_score")
        row[f"{detector}_raw_score"] = "" if raw is None else raw
        row[f"{detector}_real_prob"] = scores.get("real_prob", "")
    return row


def _save_embeddings(
    record: MediaRecord,
    detector_scores: dict[str, dict[str, Any]],
    embeddings_dir: Path,
) -> dict[str, str]:
    import numpy as np

    embeddings_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, str] = {}
    for detector in DETECTORS:
        scores = detector_scores.get(detector) or {}
        emb = scores.get("embedding")
        if emb is None:
            continue
        arr = np.asarray(emb, dtype=np.float32).reshape(-1)
        filename = (
            f"{record.dataset_id}__{safe_name(record.protocol.subgroup)}__"
            f"{record.protocol.source_id}__{record.augmentation}__{detector}.npy"
        )
        dest = embeddings_dir / filename
        np.save(dest, arr)
        paths[detector] = str(dest.resolve())
        scores["embedding_dim"] = int(arr.size)
    return paths


def score_and_embed_records(
    records: list[MediaRecord],
    *,
    scores_path: Path,
    scores_aug_path: Path,
    reps_path: Path,
    embeddings_dir: Path,
    skip_existing: bool = True,
    limit: int | None = None,
) -> dict[str, int]:
    from forensics.synthetic_image_detection.pipeline import predict_ensemble

    existing_orig = _existing_score_keys(scores_path, with_aug=False)
    existing_aug = _existing_score_keys(scores_aug_path, with_aug=True)
    existing_reps = _existing_rep_keys(reps_path)

    stats = {"scored": 0, "skipped": 0, "errors": 0}
    score_buf: list[dict[str, Any]] = []
    score_aug_buf: list[dict[str, Any]] = []
    rep_buf: list[dict[str, Any]] = []

    work = records if limit is None else records[: max(0, int(limit))]
    total = len(work)
    for idx, record in enumerate(work, start=1):
        is_aug = record.augmentation != ORIGINAL_TAG
        score_key = f"{record.sha256}|{record.augmentation}" if is_aug else record.sha256
        already_scored = score_key in (existing_aug if is_aug else existing_orig)
        already_rep = record.sample_id in existing_reps
        if skip_existing and already_scored and already_rep:
            stats["skipped"] += 1
            continue

        print(
            f"[ingest] ({idx}/{total}) scoring {record.local_path.name} "
            f"aug={record.augmentation}",
            flush=True,
        )
        t0 = time.perf_counter()
        error = ""
        detector_scores: dict[str, dict[str, Any]] = {}
        try:
            with Image.open(record.local_path) as img:
                image = img.convert("RGB")
            _table, detector_scores = predict_ensemble(
                image,
                selected_analyses=list(DETECTORS),
                return_scores=True,
                return_embedding=True,
            )
        except Exception as exc:  # noqa: BLE001 — batch job must continue
            error = str(exc)
            stats["errors"] += 1
            print(f"[ingest] ERROR {record.local_path}: {exc}", flush=True)

        elapsed = time.perf_counter() - t0
        embedding_paths: dict[str, str] = {}
        if detector_scores and not error:
            embedding_paths = _save_embeddings(record, detector_scores, embeddings_dir)

        score_row = _score_row_from_detector_scores(record, detector_scores, elapsed=elapsed, error=error)
        if is_aug:
            if not (skip_existing and already_scored):
                score_aug_buf.append(score_row)
                existing_aug.add(score_key)
        else:
            if not (skip_existing and already_scored):
                score_buf.append(score_row)
                # Originals also belong in the augmented matrix with augmentation=original
                aug_row = dict(score_row)
                aug_row["augmentation"] = ORIGINAL_TAG
                score_aug_buf.append(aug_row)
                existing_aug.add(f"{record.sha256}|{ORIGINAL_TAG}")
                existing_orig.add(record.sha256)

        if not (skip_existing and already_rep):
            rep_buf.append(
                _rep_row_from_detector_scores(
                    record, detector_scores, embedding_paths, error=error
                )
            )
            existing_reps.add(record.sample_id)

        stats["scored"] += 1
        if len(score_buf) >= 20:
            _append_csv(scores_path, SCORE_FIELDNAMES, score_buf)
            score_buf.clear()
        if len(score_aug_buf) >= 20:
            _append_csv(scores_aug_path, SCORE_AUG_FIELDNAMES, score_aug_buf)
            score_aug_buf.clear()
        if len(rep_buf) >= 20:
            _append_csv(reps_path, REP_FIELDNAMES, rep_buf)
            rep_buf.clear()

    _append_csv(scores_path, SCORE_FIELDNAMES, score_buf)
    _append_csv(scores_aug_path, SCORE_AUG_FIELDNAMES, score_aug_buf)
    _append_csv(reps_path, REP_FIELDNAMES, rep_buf)
    return stats


# ---------------------------------------------------------------------------
# Catalog registration
# ---------------------------------------------------------------------------


def register_catalog(
    *,
    base_group: str,
    dataset_id: str,
    base_id: str,
    subgroups: list[str],
    macro_id: str,
    build_root: Path,
    label: str | None = None,
) -> None:
    from core.reference_data.catalog_loader import register_base_in_macros_yaml

    register_base_in_macros_yaml(
        "synthetic_image",
        base_id=base_group,
        label=label or base_group,
        generators=sorted(set(subgroups)),
        description=f"Base ingerida via protocol CSV (dataset={dataset_id}, folder={base_id}).",
        macro_id=macro_id,
        macro_label=macro_id,
    )
    # Keep Python fallback catalog in sync for processes that skip YAML refresh.
    from core import synthetic_lr_reference as syn

    syn.REFERENCE_CATALOG[base_group] = sorted(set(subgroups))
    syn.BASE_LABELS[base_group] = label or base_group
    update_bases_json(build_root, base_id=base_id, dataset_id=dataset_id)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _default_build_root() -> Path:
    from core.reference_data.paths import get_reference_build_root

    return get_reference_build_root()


def _default_data_root() -> Path:
    from core.reference_data.paths import get_reference_data_root

    return get_reference_data_root()


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Ingere base de imagens sinteticas (protocol CSV → va-reference_build + reference_data)."
    )
    p.add_argument("--protocol", type=Path, required=True, help="CSV image_path,base_id,subgroup,y_fake")
    p.add_argument("--media-root", type=Path, default=None, help="Raiz para image_path relativos")
    p.add_argument(
        "--dataset-id",
        type=str,
        default=None,
        help="Valor da coluna dataset nos CSVs de score (default: base_group)",
    )
    p.add_argument(
        "--base-group",
        type=str,
        default=None,
        help="ID no seletor UI / macros.yaml (default: dataset-id)",
    )
    p.add_argument("--macro-id", type=str, default="other_neural", help="Macro YAML onde anexar a base")
    p.add_argument("--label", type=str, default=None, help="Rotulo amigavel no catalogo")
    p.add_argument("--reference-build-dir", type=Path, default=None)
    p.add_argument("--reference-data-dir", type=Path, default=None)
    p.add_argument("--skip-augment", action="store_true")
    p.add_argument("--skip-scoring", action="store_true", help="So materializa midia (sem GPU)")
    p.add_argument("--no-skip-existing", action="store_true", help="Reprocessa mesmo se ja existir")
    p.add_argument("--register-catalog", action="store_true")
    p.add_argument("--limit", type=int, default=None, help="Limita N registros de midia no scoring")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    protocol_rows = load_protocol_csv(args.protocol, media_root=args.media_root)
    base_id = protocol_rows[0].base_id
    base_group = args.base_group or args.dataset_id or base_id
    dataset_id = args.dataset_id or base_group

    build_root = (args.reference_build_dir or _default_build_root()).resolve()
    data_root = (args.reference_data_dir or _default_data_root()).resolve()

    scores_path = data_root / "synthetic_image" / "features" / "scores" / "lr_scores_balanced_full.csv"
    scores_aug_path = (
        data_root / "synthetic_image" / "features" / "scores" / "lr_scores_balanced_full_augmented.csv"
    )
    reps_path = data_root / "synthetic_image" / "features" / "representations" / "representations.csv"
    embeddings_dir = data_root / "synthetic_image" / "features" / "representations" / "embeddings"
    originals_manifest = build_root / "synthetic_image" / "manifests" / "originals.csv"
    augmented_manifest = build_root / "synthetic_image" / "manifests" / "augmented.csv"

    print(f"[ingest] base_id={base_id} dataset_id={dataset_id} base_group={base_group}", flush=True)
    print(f"[ingest] build_root={build_root}", flush=True)
    print(f"[ingest] data_root={data_root}", flush=True)
    print(f"[ingest] protocol rows={len(protocol_rows)}", flush=True)

    print("[ingest] materializing originals…", flush=True)
    originals = materialize_originals(protocol_rows, build_root=build_root, dataset_id=dataset_id)
    append_manifest(originals_manifest, originals)
    update_bases_json(build_root, base_id=base_id, dataset_id=dataset_id)

    augmented: list[MediaRecord] = []
    if not args.skip_augment:
        print("[ingest] generating augmentations…", flush=True)
        augmented = generate_augmentations(originals, build_root=build_root)
        append_manifest(augmented_manifest, augmented)
    else:
        print("[ingest] skip-augment", flush=True)

    if args.register_catalog:
        subgroups = sorted({row.subgroup for row in protocol_rows})
        print(f"[ingest] registering catalog macro={args.macro_id} subgroups={subgroups}", flush=True)
        register_catalog(
            base_group=base_group,
            dataset_id=dataset_id,
            base_id=base_id,
            subgroups=subgroups,
            macro_id=args.macro_id,
            build_root=build_root,
            label=args.label,
        )

    if args.skip_scoring:
        print("[ingest] skip-scoring — midia pronta", flush=True)
        return 0

    all_media = list(originals) + list(augmented)
    print(f"[ingest] scoring+embeddings on {len(all_media)} media files…", flush=True)
    stats = score_and_embed_records(
        all_media,
        scores_path=scores_path,
        scores_aug_path=scores_aug_path,
        reps_path=reps_path,
        embeddings_dir=embeddings_dir,
        skip_existing=not args.no_skip_existing,
        limit=args.limit,
    )
    print(f"[ingest] done stats={stats}", flush=True)
    print(f"[ingest] scores → {scores_path}", flush=True)
    print(f"[ingest] scores_aug → {scores_aug_path}", flush=True)
    print(f"[ingest] representations → {reps_path}", flush=True)
    return 0 if stats["errors"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
