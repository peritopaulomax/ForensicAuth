#!/usr/bin/env python3
"""Ingest an audio-spoofing reference base into ForensicAuth.

Protocol CSV (required columns, header required)::

    audio_path,base_id,subgroup,y_spoof

``y_spoof`` accepts ``0``/``1``, ``bonafide``/``spoof``, ``real``/``fake``.
Alias column ``y_fake`` is also accepted.

Optional columns::

    source_id,purpose

Pipeline order (canonical paths first, then GPU features)::

    1. Validate protocol (single ``base_id`` per run)
    2. Materialize originals → ``va-reference_build/audio_spoofing/originals/<base_id>/``
    3. Generate augs → ``.../augmented/<base_id>/``
       (mp3_128k, opus_32k, noise_snr_20, noise_snr_15)
    4. Score + embed (ForensicAuth ``run_audio_spoofing_analysis``)
       → ``reference_data/audio_spoofing/features/``
    5. Optionally register catalog (``macros.yaml``, ``bases.json``)



Example::

    conda activate va-suite
    cd "/home/bfl-pcf/VA Suite"
    PYTHONPATH=src/backend python scripts/ingest_audio_spoofing_reference.py \\
        --protocol path/to/protocol.csv \\
        --dataset-id MyAudioBench \\
        --base-group MyAudioBench \\
        --macro-id deepfake_challenges \\
        --register-catalog
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "src" / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

AUGMENTATION_NAMES: tuple[str, ...] = ("mp3_128k", "opus_32k", "noise_snr_20", "noise_snr_15")
ORIGINAL_TAG = "original"
SAMPLE_RATE = 16000

DETECTORS: tuple[str, ...] = (
    "df_arena_1b",
    "sls_xlsr",
    "wedefense_wavlm_mhfa",
    "tfcl_xlsr",
)

PROTOCOL_REQUIRED_PATH = "audio_path"
PROTOCOL_REQUIRED_BASE = "base_id"
PROTOCOL_REQUIRED_SUBGROUP = "subgroup"

SCORE_FIELDNAMES: list[str] = [
    "dataset",
    "purpose",
    "reference_split",
    "generator",
    "subset",
    "label",
    "label_name",
    "y_spoof",
    "source_id",
    "source_path",
    "audio_path",
    "audio_sha256",
    "error",
    "elapsed_seconds",
    "df_arena_1b_spoof_prob",
    "df_arena_1b_bonafide_prob",
    "df_arena_1b_spoof_logit",
    "df_arena_1b_bonafide_logit",
    "df_arena_1b_decision",
    "df_arena_1b_device",
    "df_arena_1b_window_count",
    "sls_xlsr_spoof_prob",
    "sls_xlsr_bonafide_prob",
    "sls_xlsr_spoof_logit",
    "sls_xlsr_bonafide_logit",
    "sls_xlsr_decision",
    "sls_xlsr_device",
    "sls_xlsr_window_count",
    "wedefense_wavlm_mhfa_spoof_prob",
    "wedefense_wavlm_mhfa_bonafide_prob",
    "wedefense_wavlm_mhfa_spoof_logit",
    "wedefense_wavlm_mhfa_bonafide_logit",
    "wedefense_wavlm_mhfa_decision",
    "wedefense_wavlm_mhfa_device",
    "wedefense_wavlm_mhfa_window_count",
    # Keep meta block before TFCL to match existing lr_scores_balanced_full.csv header.
    # Appending with a different column order silently misaligns values (DictWriter).
    "augmentation",
    "augmentation_params",
    "source_sha256",
    "parent_source_id",
    "tfcl_xlsr_spoof_prob",
    "tfcl_xlsr_bonafide_prob",
    "tfcl_xlsr_spoof_logit",
    "tfcl_xlsr_bonafide_logit",
    "tfcl_xlsr_decision",
    "tfcl_xlsr_device",
    "tfcl_xlsr_window_count",
]

REP_FIELDNAMES: list[str] = [
    "audio_path",
    "augmentation",
    "dataset",
    "df_arena_1b_bonafide_logit",
    "df_arena_1b_bonafide_prob",
    "df_arena_1b_embedding_dim",
    "df_arena_1b_embedding_path",
    "df_arena_1b_spoof_logit",
    "elapsed_seconds",
    "error",
    "generator",
    "label",
    "label_name",
    "purpose",
    "reference_split",
    "sample_id",
    "sls_xlsr_bonafide_logit",
    "sls_xlsr_bonafide_prob",
    "sls_xlsr_embedding_dim",
    "sls_xlsr_embedding_path",
    "sls_xlsr_spoof_logit",
    "source_id",
    "source_path",
    "wedefense_wavlm_mhfa_bonafide_logit",
    "wedefense_wavlm_mhfa_bonafide_prob",
    "wedefense_wavlm_mhfa_embedding_dim",
    "wedefense_wavlm_mhfa_embedding_path",
    "wedefense_wavlm_mhfa_spoof_logit",
    # Keep y_spoof/merge_source before TFCL to match existing representations.csv header.
    "y_spoof",
    "merge_source",
    "tfcl_xlsr_bonafide_logit",
    "tfcl_xlsr_bonafide_prob",
    "tfcl_xlsr_embedding_dim",
    "tfcl_xlsr_embedding_path",
    "tfcl_xlsr_spoof_logit",
]

MANIFEST_ORIG_FIELDNAMES: list[str] = [
    "base_id",
    "dataset",
    "generator",
    "label",
    "y_spoof",
    "source_id",
    "local_relpath",
    "status",
    "sha256",
    "bytes",
    "source_path",
]

MANIFEST_AUG_FIELDNAMES: list[str] = [
    "base_id",
    "dataset",
    "generator",
    "label",
    "y_spoof",
    "source_id",
    "parent_source_id",
    "augmentation",
    "augmentation_params",
    "local_relpath",
    "sha256",
    "source_path",
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_name(text: str, max_len: int = 120) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "._-+" else "_" for ch in str(text).strip())
    cleaned = cleaned.strip("._") or "item"
    return cleaned[:max_len]


def parse_y_spoof(raw: Any) -> int:
    text = str(raw).strip().lower()
    if text in {"1", "true", "spoof", "fake", "synthetic", "ai"}:
        return 1
    if text in {"0", "false", "bonafide", "real", "authentic", "nature"}:
        return 0
    raise ValueError(f"y_spoof invalido: {raw!r} (use 0/1, bonafide/spoof, real/fake)")


def label_for_y_spoof(y_spoof: int) -> str:
    return "spoof" if int(y_spoof) == 1 else "bonafide"


@dataclass(frozen=True)
class ProtocolRow:
    audio_path: Path
    base_id: str
    subgroup: str
    y_spoof: int
    source_id: str
    purpose: str
    row_index: int


def load_protocol_csv(path: Path, *, media_root: Path | None = None) -> list[ProtocolRow]:
    if not path.is_file():
        raise FileNotFoundError(f"Protocolo nao encontrado: {path}")
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            raise ValueError("Protocolo CSV sem cabecalho")
        fields = {name.strip() for name in reader.fieldnames}
        if PROTOCOL_REQUIRED_PATH not in fields:
            raise ValueError("Protocolo CSV precisa da coluna audio_path")
        if PROTOCOL_REQUIRED_BASE not in fields or PROTOCOL_REQUIRED_SUBGROUP not in fields:
            raise ValueError("Protocolo CSV precisa das colunas base_id e subgroup")
        if "y_spoof" not in fields and "y_fake" not in fields:
            raise ValueError("Protocolo CSV precisa de y_spoof (ou alias y_fake)")

        rows: list[ProtocolRow] = []
        for idx, raw in enumerate(reader, start=1):
            audio_raw = str(raw.get("audio_path") or "").strip()
            if not audio_raw:
                raise ValueError(f"Linha {idx}: audio_path vazio")
            audio_path = Path(audio_raw).expanduser()
            if not audio_path.is_absolute() and media_root is not None:
                audio_path = (media_root / audio_path).resolve()
            else:
                audio_path = audio_path.resolve()
            base_id = safe_name(str(raw.get("base_id") or "").strip().lower().replace("-", "_"))
            subgroup = str(raw.get("subgroup") or "").strip() or "default"
            y_raw = raw.get("y_spoof") if raw.get("y_spoof") not in (None, "") else raw.get("y_fake")
            y_spoof = parse_y_spoof(y_raw)
            source_id = str(raw.get("source_id") or "").strip() or f"row_{idx}"
            purpose = str(raw.get("purpose") or "").strip() or "reference_population"
            if not base_id:
                raise ValueError(f"Linha {idx}: base_id vazio")
            rows.append(
                ProtocolRow(
                    audio_path=audio_path,
                    base_id=base_id,
                    subgroup=subgroup,
                    y_spoof=y_spoof,
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
    missing = [str(row.audio_path) for row in rows if not row.audio_path.is_file()]
    if missing:
        preview = ", ".join(missing[:5])
        more = f" (+{len(missing) - 5} outros)" if len(missing) > 5 else ""
        raise FileNotFoundError(f"Audios ausentes no protocolo: {preview}{more}")
    return rows


# ---------------------------------------------------------------------------
# Augmentations (reimplemented — not imported from ops)
# ---------------------------------------------------------------------------


def _require_ffmpeg() -> str:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg ausente — necessario para mp3_128k e opus_32k")
    return ffmpeg


def _stable_seed(*parts: str) -> int:
    digest = hashlib.sha256("||".join(parts).encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def _to_mono_float32(audio: np.ndarray) -> np.ndarray:
    arr = np.asarray(audio, dtype=np.float32)
    if arr.ndim > 1:
        arr = arr.mean(axis=1)
    return arr.astype(np.float32, copy=False)


def _resample_if_needed(audio: np.ndarray, sr: int, target_sr: int = SAMPLE_RATE) -> tuple[np.ndarray, int]:
    if int(sr) == int(target_sr):
        return _to_mono_float32(audio), target_sr
    import librosa

    resampled = librosa.resample(_to_mono_float32(audio), orig_sr=int(sr), target_sr=target_sr)
    return resampled.astype(np.float32), target_sr


def _write_wav(path: Path, audio: np.ndarray, sr: int = SAMPLE_RATE) -> None:
    import soundfile as sf

    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), _to_mono_float32(audio), int(sr), subtype="PCM_16")


def _read_audio(path: Path) -> tuple[np.ndarray, int]:
    import soundfile as sf

    audio, sr = sf.read(str(path), always_2d=False)
    return _to_mono_float32(audio), int(sr)


def _pink_noise(length: int, rng: np.random.Generator) -> np.ndarray:
    white = rng.standard_normal(length).astype(np.float32)
    if length <= 1:
        return white
    pink = np.cumsum(white)
    peak = float(np.max(np.abs(pink))) or 1.0
    return (pink / peak).astype(np.float32)


def mix_noise_at_snr(audio: np.ndarray, *, snr_db: float, seed: int) -> tuple[np.ndarray, dict[str, Any]]:
    clean = _to_mono_float32(audio)
    rng = np.random.default_rng(seed)
    noise = _pink_noise(len(clean), rng)
    signal_power = float(np.mean(clean**2)) + 1e-12
    noise_power = float(np.mean(noise**2)) + 1e-12
    target_noise_power = signal_power / (10.0 ** (snr_db / 10.0))
    scale = float(np.sqrt(target_noise_power / noise_power))
    noisy = np.clip(clean + noise * scale, -1.0, 1.0).astype(np.float32)
    params = {
        "noise_type": "pink",
        "snr_db": float(snr_db),
        "seed": int(seed),
        "signal_power": signal_power,
        "noise_power": target_noise_power,
    }
    return noisy, params


def _ffmpeg_codec_roundtrip(
    audio: np.ndarray,
    sr: int,
    *,
    suffix: str,
    codec_args: list[str],
) -> tuple[np.ndarray, int]:
    ffmpeg = _require_ffmpeg()
    clean, out_sr = _resample_if_needed(audio, sr)
    with tempfile.TemporaryDirectory(prefix="va_audio_aug_") as tmp:
        tmp_path = Path(tmp)
        src = tmp_path / "src.wav"
        coded = tmp_path / f"out{suffix}"
        dst = tmp_path / "dst.wav"
        _write_wav(src, clean, out_sr)
        subprocess.run(
            [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(src), *codec_args, str(coded)],
            check=True,
        )
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(coded),
                "-ac",
                "1",
                "-ar",
                str(SAMPLE_RATE),
                str(dst),
            ],
            check=True,
        )
        return _read_audio(dst)


def apply_augmentation(
    audio: np.ndarray,
    sr: int,
    aug: str,
    *,
    source_id: str = "",
    source_sha256: str = "",
) -> tuple[np.ndarray, int, dict[str, Any]]:
    if aug not in AUGMENTATION_NAMES:
        raise ValueError(f"Augmentacao desconhecida: {aug}")

    if aug == "mp3_128k":
        out, out_sr = _ffmpeg_codec_roundtrip(
            audio, sr, suffix=".mp3", codec_args=["-codec:a", "libmp3lame", "-b:a", "128k"]
        )
        return out, out_sr, {"codec": "libmp3lame", "bitrate_kbps": 128, "roundtrip": "wav->mp3->wav"}

    if aug == "opus_32k":
        out, out_sr = _ffmpeg_codec_roundtrip(
            audio,
            sr,
            suffix=".opus",
            codec_args=["-codec:a", "libopus", "-b:a", "32k", "-application", "voip"],
        )
        return (
            out,
            out_sr,
            {"codec": "libopus", "bitrate_kbps": 32, "application": "voip", "roundtrip": "wav->opus->wav"},
        )

    clean, out_sr = _resample_if_needed(audio, sr)
    seed = _stable_seed(source_id, source_sha256, aug)
    if aug == "noise_snr_20":
        out, params = mix_noise_at_snr(clean, snr_db=20.0, seed=seed)
        return out, out_sr, params
    if aug == "noise_snr_15":
        out, params = mix_noise_at_snr(clean, snr_db=15.0, seed=seed)
        return out, out_sr, params
    raise ValueError(f"Augmentacao desconhecida: {aug}")


# ---------------------------------------------------------------------------
# Materialize
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
        return (
            f"{self.dataset_id}__{safe_name(self.protocol.subgroup)}__"
            f"{self.protocol.source_id}__{self.augmentation}"
        )

    @property
    def parent_source_id(self) -> str:
        return self.protocol.source_id


def _original_dest(build_root: Path, row: ProtocolRow, *, digest12: str) -> tuple[Path, str]:
    label = label_for_y_spoof(row.y_spoof)
    ext = row.audio_path.suffix.lower() or ".wav"
    filename = f"{digest12}__{safe_name(row.audio_path.stem)}{ext}"
    rel = (
        Path("audio_spoofing")
        / "originals"
        / row.base_id
        / safe_name(row.subgroup)
        / label
        / filename
    )
    return build_root / rel, str(rel).replace("\\", "/")


def _aug_dest(build_root: Path, row: ProtocolRow, *, aug: str, digest12: str) -> tuple[Path, str]:
    label = label_for_y_spoof(row.y_spoof)
    filename = f"{row.source_id}__{aug}__{digest12}.wav"
    rel = (
        Path("audio_spoofing")
        / "augmented"
        / row.base_id
        / safe_name(row.subgroup)
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
        digest = sha256_file(row.audio_path)
        dest, rel = _original_dest(build_root, row, digest12=digest[:12])
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.is_file() or sha256_file(dest) != digest:
            shutil.copy2(row.audio_path, dest)
        out.append(
            MediaRecord(
                protocol=row,
                dataset_id=dataset_id,
                local_path=dest.resolve(),
                local_relpath=rel,
                sha256=digest,
                nbytes=dest.stat().st_size,
                source_sha256=digest,
                source_path=str(row.audio_path),
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
        audio, sr = _read_audio(record.local_path)
        for aug in AUGMENTATION_NAMES:
            aug_audio, aug_sr, params = apply_augmentation(
                audio,
                sr,
                aug,
                source_id=record.protocol.source_id,
                source_sha256=record.sha256,
            )
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp_path = Path(tmp.name)
            try:
                _write_wav(tmp_path, aug_audio, aug_sr)
                digest = sha256_file(tmp_path)
                dest, rel = _aug_dest(
                    build_root, record.protocol, aug=aug, digest12=digest[:12]
                )
                dest.parent.mkdir(parents=True, exist_ok=True)
                if not dest.is_file() or sha256_file(dest) != digest:
                    shutil.move(str(tmp_path), str(dest))
                else:
                    tmp_path.unlink(missing_ok=True)
            finally:
                if tmp_path.exists():
                    tmp_path.unlink(missing_ok=True)
            out.append(
                MediaRecord(
                    protocol=record.protocol,
                    dataset_id=record.dataset_id,
                    local_path=dest.resolve(),
                    local_relpath=rel,
                    sha256=digest,
                    nbytes=dest.stat().st_size,
                    source_sha256=record.sha256,
                    source_path=str(record.local_path),
                    augmentation=aug,
                    augmentation_params=params,
                )
            )
    return out


def append_manifest_originals(path: Path, records: Iterable[MediaRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: set[str] = set()
    if path.is_file():
        with path.open("r", encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                existing.add(str(row.get("local_relpath") or ""))
    write_header = not path.is_file() or path.stat().st_size == 0
    with path.open("a", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=MANIFEST_ORIG_FIELDNAMES)
        if write_header:
            writer.writeheader()
        for record in records:
            if record.local_relpath in existing:
                continue
            writer.writerow(
                {
                    "base_id": record.protocol.base_id,
                    "dataset": record.dataset_id,
                    "generator": record.protocol.subgroup,
                    "label": label_for_y_spoof(record.protocol.y_spoof),
                    "y_spoof": int(record.protocol.y_spoof),
                    "source_id": record.protocol.source_id,
                    "local_relpath": record.local_relpath,
                    "status": "ok",
                    "sha256": record.sha256,
                    "bytes": record.nbytes,
                    "source_path": record.source_path,
                }
            )
            existing.add(record.local_relpath)


def append_manifest_augmented(path: Path, records: Iterable[MediaRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: set[str] = set()
    if path.is_file():
        with path.open("r", encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                existing.add(str(row.get("local_relpath") or ""))
    write_header = not path.is_file() or path.stat().st_size == 0
    with path.open("a", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=MANIFEST_AUG_FIELDNAMES)
        if write_header:
            writer.writeheader()
        for record in records:
            if record.local_relpath in existing:
                continue
            writer.writerow(
                {
                    "base_id": record.protocol.base_id,
                    "dataset": record.dataset_id,
                    "generator": record.protocol.subgroup,
                    "label": label_for_y_spoof(record.protocol.y_spoof),
                    "y_spoof": int(record.protocol.y_spoof),
                    "source_id": f"{record.protocol.source_id}_{record.augmentation}",
                    "parent_source_id": record.parent_source_id,
                    "augmentation": record.augmentation,
                    "augmentation_params": json.dumps(record.augmentation_params, sort_keys=True),
                    "local_relpath": record.local_relpath,
                    "sha256": record.sha256,
                    "source_path": record.source_path,
                }
            )
            existing.add(record.local_relpath)


def update_bases_json(build_root: Path, *, base_id: str, dataset_id: str) -> None:
    path = build_root / "bases.json"
    if path.is_file():
        doc = json.loads(path.read_text(encoding="utf-8"))
    else:
        doc = {"root": str(build_root), "audio_spoofing": {}, "synthetic_image": {}}
    audio = doc.setdefault("audio_spoofing", {})
    bases = list(audio.get("bases") or [])
    if base_id not in bases:
        bases.append(base_id)
        bases.sort()
    audio["bases"] = bases
    mapping = dict(audio.get("dataset_id_map") or {})
    mapping[dataset_id] = base_id
    # Keep reverse lookup style used by existing file (dataset → base_id folder)
    # Also store folder → dataset for new ingestions.
    folder_map = dict(audio.get("folder_to_dataset") or {})
    folder_map[base_id] = dataset_id
    audio["folder_to_dataset"] = folder_map
    audio["dataset_id_map"] = mapping
    doc["root"] = str(build_root)
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Scoring / embeddings
# ---------------------------------------------------------------------------


def _existing_score_keys(path: Path) -> set[str]:
    keys: set[str] = set()
    if not path.is_file() or path.stat().st_size == 0:
        return keys
    with path.open("r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            sha = str(row.get("audio_sha256") or "")
            aug = str(row.get("augmentation") or ORIGINAL_TAG).strip() or ORIGINAL_TAG
            if sha:
                keys.add(f"{sha}|{aug}")
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
    out_fields = list(fieldnames)
    if not write_header:
        with path.open("r", encoding="utf-8", newline="") as existing:
            reader = csv.DictReader(existing)
            if reader.fieldnames:
                # Preserve on-disk column order; only append unknown fields at the end.
                out_fields = list(reader.fieldnames)
                for key in fieldnames:
                    if key not in out_fields:
                        out_fields.append(key)
    with path.open("a", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=out_fields, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in out_fields})


def _embeddings_dir_for(record: MediaRecord, reps_root: Path) -> Path:
    if record.augmentation == ORIGINAL_TAG:
        return reps_root / "originals" / "embeddings"
    return reps_root / "augmented" / "embeddings"


def _save_embeddings(
    record: MediaRecord,
    detector_scores: dict[str, dict[str, Any]],
    reps_root: Path,
) -> dict[str, str]:
    emb_dir = _embeddings_dir_for(record, reps_root)
    emb_dir.mkdir(parents=True, exist_ok=True)
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
        dest = emb_dir / filename
        np.save(dest, arr)
        paths[detector] = str(dest.resolve())
        scores["embedding_dim"] = int(arr.size)
    return paths


def _score_row(
    record: MediaRecord,
    detector_scores: dict[str, dict[str, Any]],
    *,
    elapsed: float,
    error: str = "",
) -> dict[str, Any]:
    label = label_for_y_spoof(record.protocol.y_spoof)
    row: dict[str, Any] = {
        "dataset": record.dataset_id,
        "purpose": record.protocol.purpose,
        "reference_split": record.protocol.purpose,
        "generator": record.protocol.subgroup,
        "subset": record.protocol.subgroup,
        "label": label,
        "label_name": label,
        "y_spoof": int(record.protocol.y_spoof),
        "source_id": record.protocol.source_id
        if record.augmentation == ORIGINAL_TAG
        else f"{record.protocol.source_id}_{record.augmentation}",
        "source_path": record.source_path,
        "audio_path": str(record.local_path),
        "audio_sha256": record.sha256,
        "error": error,
        "elapsed_seconds": round(float(elapsed), 6),
        "augmentation": "" if record.augmentation == ORIGINAL_TAG else record.augmentation,
        "augmentation_params": json.dumps(record.augmentation_params, sort_keys=True)
        if record.augmentation_params
        else "",
        "source_sha256": record.source_sha256,
        "parent_source_id": ""
        if record.augmentation == ORIGINAL_TAG
        else record.parent_source_id,
    }
    for detector in DETECTORS:
        scores = detector_scores.get(detector) or {}
        row[f"{detector}_spoof_prob"] = scores.get("spoof_prob", "")
        row[f"{detector}_bonafide_prob"] = scores.get("bonafide_prob", "")
        row[f"{detector}_spoof_logit"] = scores.get("spoof_logit", "")
        row[f"{detector}_bonafide_logit"] = scores.get("bonafide_logit", "")
        row[f"{detector}_decision"] = scores.get("decision", "")
        row[f"{detector}_device"] = scores.get("device", "")
        row[f"{detector}_window_count"] = scores.get("window_count", "")
    return row


def _rep_row(
    record: MediaRecord,
    detector_scores: dict[str, dict[str, Any]],
    embedding_paths: dict[str, str],
    *,
    elapsed: float,
    error: str = "",
) -> dict[str, Any]:
    label = label_for_y_spoof(record.protocol.y_spoof)
    row: dict[str, Any] = {
        "audio_path": str(record.local_path),
        "augmentation": record.augmentation,
        "dataset": record.dataset_id,
        "elapsed_seconds": round(float(elapsed), 6),
        "error": error,
        "generator": record.protocol.subgroup,
        "label": label,
        "label_name": label,
        "purpose": record.protocol.purpose,
        "reference_split": record.protocol.purpose,
        "sample_id": record.sample_id,
        "source_id": record.protocol.source_id,
        "source_path": record.source_path,
        "y_spoof": int(record.protocol.y_spoof),
        "merge_source": "originals" if record.augmentation == ORIGINAL_TAG else "augmented",
    }
    for detector in DETECTORS:
        scores = detector_scores.get(detector) or {}
        row[f"{detector}_spoof_logit"] = scores.get("spoof_logit", "")
        row[f"{detector}_bonafide_logit"] = scores.get("bonafide_logit", "")
        row[f"{detector}_bonafide_prob"] = scores.get("bonafide_prob", "")
        row[f"{detector}_embedding_dim"] = scores.get("embedding_dim", "")
        row[f"{detector}_embedding_path"] = embedding_paths.get(detector, "")
    return row


def score_and_embed_records(
    records: list[MediaRecord],
    *,
    scores_path: Path,
    reps_path: Path,
    reps_root: Path,
    skip_existing: bool = True,
    limit: int | None = None,
    window_seconds: float = 4.0,
) -> dict[str, int]:
    from forensics.audio_spoofing.pipeline import run_audio_spoofing_analysis

    existing_scores = _existing_score_keys(scores_path)
    existing_reps = _existing_rep_keys(reps_path)
    stats = {"scored": 0, "skipped": 0, "errors": 0}
    score_buf: list[dict[str, Any]] = []
    rep_buf: list[dict[str, Any]] = []

    work = records if limit is None else records[: max(0, int(limit))]
    total = len(work)
    for idx, record in enumerate(work, start=1):
        aug_key = record.augmentation
        score_key = f"{record.sha256}|{aug_key}"
        already_scored = score_key in existing_scores
        already_rep = record.sample_id in existing_reps
        if skip_existing and already_scored and already_rep:
            stats["skipped"] += 1
            continue

        print(
            f"[ingest-audio] ({idx}/{total}) scoring {record.local_path.name} aug={record.augmentation}",
            flush=True,
        )
        t0 = time.perf_counter()
        error = ""
        detector_scores: dict[str, dict[str, Any]] = {}
        try:
            audio, sr = _read_audio(record.local_path)
            audio, sr = _resample_if_needed(audio, sr)
            result = run_audio_spoofing_analysis(
                audio,
                sr,
                window_seconds=window_seconds,
                selected_analyses=list(DETECTORS),
                return_embedding=True,
            )
            detector_scores = result.get("detector_scores") or {}
        except Exception as exc:  # noqa: BLE001
            error = str(exc)
            stats["errors"] += 1
            print(f"[ingest-audio] ERROR {record.local_path}: {exc}", flush=True)

        elapsed = time.perf_counter() - t0
        embedding_paths: dict[str, str] = {}
        if detector_scores and not error:
            embedding_paths = _save_embeddings(record, detector_scores, reps_root)

        if not (skip_existing and already_scored):
            score_buf.append(_score_row(record, detector_scores, elapsed=elapsed, error=error))
            existing_scores.add(score_key)
        if not (skip_existing and already_rep):
            rep_buf.append(
                _rep_row(
                    record,
                    detector_scores,
                    embedding_paths,
                    elapsed=elapsed,
                    error=error,
                )
            )
            existing_reps.add(record.sample_id)

        stats["scored"] += 1
        if len(score_buf) >= 16:
            _append_csv(scores_path, SCORE_FIELDNAMES, score_buf)
            score_buf.clear()
        if len(rep_buf) >= 16:
            _append_csv(reps_path, REP_FIELDNAMES, rep_buf)
            rep_buf.clear()

    _append_csv(scores_path, SCORE_FIELDNAMES, score_buf)
    _append_csv(reps_path, REP_FIELDNAMES, rep_buf)
    return stats


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
    from core import audio_spoofing_lr_reference as audio_ref

    register_base_in_macros_yaml(
        "audio_spoofing",
        base_id=base_group,
        label=label or base_group,
        generators=sorted(set(subgroups)),
        description=f"Base ingerida via protocol CSV (dataset={dataset_id}, folder={base_id}).",
        macro_id=macro_id,
        macro_label=macro_id,
    )
    audio_ref.REFERENCE_GENERATORS[base_group] = sorted(set(subgroups))
    audio_ref.BASE_LABELS[base_group] = label or base_group
    update_bases_json(build_root, base_id=base_id, dataset_id=dataset_id)


def _default_build_root() -> Path:
    from core.reference_data.paths import get_reference_build_root

    return get_reference_build_root()


def _default_data_root() -> Path:
    from core.reference_data.paths import get_reference_data_root

    return get_reference_data_root()


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Ingere base de spoofing de audio (protocol CSV → va-reference_build + reference_data)."
    )
    p.add_argument("--protocol", type=Path, required=True, help="CSV audio_path,base_id,subgroup,y_spoof")
    p.add_argument("--media-root", type=Path, default=None)
    p.add_argument("--dataset-id", type=str, default=None)
    p.add_argument("--base-group", type=str, default=None)
    p.add_argument("--macro-id", type=str, default="deepfake_challenges")
    p.add_argument("--label", type=str, default=None)
    p.add_argument("--reference-build-dir", type=Path, default=None)
    p.add_argument("--reference-data-dir", type=Path, default=None)
    p.add_argument("--skip-augment", action="store_true")
    p.add_argument("--skip-scoring", action="store_true")
    p.add_argument("--no-skip-existing", action="store_true")
    p.add_argument("--register-catalog", action="store_true")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--window-seconds", type=float, default=4.0)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    protocol_rows = load_protocol_csv(args.protocol, media_root=args.media_root)
    base_id = protocol_rows[0].base_id
    base_group = args.base_group or args.dataset_id or base_id
    dataset_id = args.dataset_id or base_group

    build_root = (args.reference_build_dir or _default_build_root()).resolve()
    data_root = (args.reference_data_dir or _default_data_root()).resolve()

    scores_path = data_root / "audio_spoofing" / "features" / "scores" / "lr_scores_balanced_full.csv"
    reps_root = data_root / "audio_spoofing" / "features" / "representations"
    reps_path = reps_root / "representations.csv"
    originals_manifest = build_root / "audio_spoofing" / "manifests" / "originals.csv"
    augmented_manifest = build_root / "audio_spoofing" / "manifests" / "augmented.csv"

    print(f"[ingest-audio] base_id={base_id} dataset_id={dataset_id} base_group={base_group}", flush=True)
    print(f"[ingest-audio] build_root={build_root}", flush=True)
    print(f"[ingest-audio] data_root={data_root}", flush=True)
    print(f"[ingest-audio] protocol rows={len(protocol_rows)}", flush=True)

    print("[ingest-audio] materializing originals…", flush=True)
    originals = materialize_originals(protocol_rows, build_root=build_root, dataset_id=dataset_id)
    append_manifest_originals(originals_manifest, originals)
    update_bases_json(build_root, base_id=base_id, dataset_id=dataset_id)

    augmented: list[MediaRecord] = []
    if not args.skip_augment:
        print("[ingest-audio] generating augmentations…", flush=True)
        augmented = generate_augmentations(originals, build_root=build_root)
        append_manifest_augmented(augmented_manifest, augmented)
    else:
        print("[ingest-audio] skip-augment", flush=True)

    if args.register_catalog:
        subgroups = sorted({row.subgroup for row in protocol_rows})
        print(f"[ingest-audio] registering catalog macro={args.macro_id} subgroups={subgroups}", flush=True)
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
        print("[ingest-audio] skip-scoring — midia pronta", flush=True)
        return 0

    all_media = list(originals) + list(augmented)
    print(f"[ingest-audio] scoring+embeddings on {len(all_media)} media files…", flush=True)
    stats = score_and_embed_records(
        all_media,
        scores_path=scores_path,
        reps_path=reps_path,
        reps_root=reps_root,
        skip_existing=not args.no_skip_existing,
        limit=args.limit,
        window_seconds=float(args.window_seconds),
    )
    print(f"[ingest-audio] done stats={stats}", flush=True)
    print(f"[ingest-audio] scores → {scores_path}", flush=True)
    print(f"[ingest-audio] representations → {reps_path}", flush=True)
    return 0 if stats["errors"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
