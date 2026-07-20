#!/usr/bin/env python3
"""Shared helpers for audio spoofing LR calibration datasets."""

from __future__ import annotations

import csv
import hashlib
import json
import random
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import yaml

AUDIO_EXTENSIONS = {".wav", ".flac", ".mp3", ".ogg", ".opus", ".m4a"}

DETECTORS = ("df_arena_1b", "sls_xlsr", "wedefense_wavlm_mhfa")
DETECTOR_LABELS = {
    "df_arena_1b": "DF Arena 1B",
    "sls_xlsr": "SLS XLS-R",
    "wedefense_wavlm_mhfa": "WeDefense WavLM+MHFA",
}

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "audio_lr_protocolo.yaml"
EXAMPLE_CONFIG = PROJECT_ROOT / "config" / "audio_lr_protocolo.example.yaml"

BASE_LABELS: dict[str, str] = {
    "ASVspoof2019_LA": "ASVspoof 2019 LA",
    "ASVspoof2021_LA_eval": "ASVspoof 2021 LA eval",
    "ASVspoof5": "ASVspoof 5",
    "CodecFake": "CodecFake",
    "ADD2022": "ADD 2022",
    "ADD2023": "ADD 2023",
    "DFADD": "DFADD",
    "SONAR": "SONAR",
    "In-The-Wild": "In-The-Wild",
    "Fake-or-Real": "Fake-or-Real",
    "LibriSeVoc": "LibriSeVoc",
}

BASE_CATALOG: dict[str, dict[str, str]] = {
    "ASVspoof2019_LA": {
        "description": "Logical access ASVspoof 2019 — TTS/VC clássico.",
        "paper_title": "ASVspoof 2019: Future Horizons in Spoofed and Countermeasure Speech",
        "paper_url": "https://www.asvspoof.org/",
    },
    "ASVspoof2021_LA_eval": {
        "description": "ASVspoof 2021 LA evaluation — ataques neural TTS/VC.",
        "paper_title": "ASVspoof 2021",
        "paper_url": "https://www.asvspoof.org/",
    },
    "ASVspoof5": {
        "description": "ASVspoof 5 evaluation (flac_E_eval) — deepfakes recentes.",
        "paper_title": "ASVspoof 5",
        "paper_url": "https://www.asvspoof.org/",
    },
    "CodecFake": {
        "description": "CodecFake — spoofing sob diferentes condições de codec (C1–C7).",
        "paper_title": "CodecFake",
        "paper_url": "",
    },
    "ADD2022": {
        "description": "Audio Deepfake Detection 2022 — tracks 1 e 32.",
        "paper_title": "ADD 2022",
        "paper_url": "",
    },
    "ADD2023": {
        "description": "Audio Deepfake Detection 2023.",
        "paper_title": "ADD 2023",
        "paper_url": "",
    },
    "DFADD": {
        "description": "Deepfake ADD com geradores nomeados no arquivo (GradTTS, etc.).",
        "paper_title": "DFADD",
        "paper_url": "",
    },
    "SONAR": {
        "description": "SONAR — múltiplos geradores TTS (PromptTTS2, etc.).",
        "paper_title": "SONAR",
        "paper_url": "",
    },
    "In-The-Wild": {
        "description": "Áudio in-the-wild (YouTube, podcasts).",
        "paper_title": "In-The-Wild Spoofing",
        "paper_url": "",
    },
    "Fake-or-Real": {
        "description": "Fake-or-Real benchmark.",
        "paper_title": "Fake-or-Real",
        "paper_url": "",
    },
    "LibriSeVoc": {
        "description": "LibriSeVoc — vocoder-based spoofing.",
        "paper_title": "LibriSeVoc",
        "paper_url": "",
    },
}

REFERENCE_MACRO_CATEGORIES: dict[str, dict[str, Any]] = {
    "asv_classic": {
        "label": "ASVspoof (LA clássico)",
        "description": "Desafios ASVspoof logical access — referência histórica de CM.",
        "datasets": ["ASVspoof2019_LA", "ASVspoof2021_LA_eval", "ASVspoof5"],
    },
    "codec_conditions": {
        "label": "Codec / canal",
        "description": "CodecFake — variação de codec/transmissão (C1–C7).",
        "datasets": ["CodecFake"],
    },
    "deepfake_challenges": {
        "label": "Desafios deepfake (ADD/DFADD/SONAR)",
        "description": "Competições ADD e benchmarks com geradores explícitos.",
        "datasets": ["ADD2022", "ADD2023", "DFADD", "SONAR"],
    },
    "in_the_wild": {
        "label": "In-the-wild / misc",
        "description": "Dados menos controlados ou vocoder-based.",
        "datasets": ["In-The-Wild", "Fake-or-Real", "LibriSeVoc"],
    },
}


@dataclass(frozen=True)
class PopulationItem:
    base_group: str
    subgroup: str

    @property
    def key(self) -> str:
        return f"{self.base_group}/{self.subgroup}"


def safe_name(value: Any) -> str:
    text = str(value).strip()
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", text).strip("_") or "unknown"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_config(path: Path | None = None) -> dict[str, Any]:
    cfg_path = path or DEFAULT_CONFIG
    if not cfg_path.exists():
        cfg_path = EXAMPLE_CONFIG
    with cfg_path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def resolve_audio_path(file_path: str, config: dict[str, Any]) -> Path:
    path = Path(file_path)
    for mapping in config.get("path_prefixes") or []:
        remote = str(mapping.get("remote", "")).rstrip("/")
        local = str(mapping.get("local", "")).rstrip("/")
        if remote and local and str(path).startswith(remote):
            return Path(local + str(path)[len(remote) :])
    return path


def infer_generator(row: dict[str, Any]) -> str:
    dataset = str(row.get("dataset", ""))
    subset = str(row.get("subset", "") or "").strip()
    path = str(row.get("file_path", ""))
    stem = Path(path).stem

    if dataset == "DFADD" and "_" in stem:
        return stem.rsplit("_", 1)[-1]
    if dataset == "SONAR":
        parent = Path(path).parent.name
        if parent and parent != "SONAR_dataset":
            return parent
    if dataset == "CodecFake" and subset:
        return subset
    if dataset == "SONAR" and subset == "real_samples":
        return "real_samples"
    if not subset or subset.lower() == "nan":
        if dataset == "ASVspoof2021_LA_eval":
            return "LA_eval"
        if dataset in ("In-The-Wild", "Fake-or-Real"):
            return dataset
        return dataset or "unknown"
    if subset:
        return subset


# Pools de bonafide compartilhados quando o gerador só contém spoof (SONAR, LibriSeVoc, DFADD).
BONAFIDE_POOL_GENERATOR: dict[str, str] = {
    "SONAR": "real_samples",
    "LibriSeVoc": "gt",
}

# DFADD usa todos os bonafide do dataset como pool para cada gerador TTS.
BONAFIDE_POOL_DATASET: set[str] = {"DFADD"}

CODEC_CONDITION_LABELS: dict[str, str] = {
    "C1": "Codec neural C1",
    "C2": "Codec neural C2",
    "C3": "Codec neural C3",
    "C4": "Codec neural C4",
    "C5": "Codec neural C5",
    "C6": "Codec neural C6",
    "C7": "Codec neural C7",
}


def label_to_y_spoof(label: str) -> int:
    return 1 if str(label).strip().lower() == "spoof" else 0


def audio_duration_seconds(path: Path) -> float | None:
    try:
        import soundfile as sf

        return float(sf.info(str(path)).duration)
    except Exception:
        try:
            import librosa

            return float(librosa.get_duration(path=str(path)))
        except Exception:
            return None


def filter_min_duration(
    df: pd.DataFrame,
    config: dict[str, Any],
    *,
    min_seconds: float | None = None,
) -> pd.DataFrame:
    threshold = float(min_seconds if min_seconds is not None else config.get("min_duration_seconds", 0) or 0)
    if threshold <= 0:
        return df
    keep: list[int] = []
    for idx, row in df.iterrows():
        resolved = resolve_audio_path(str(row["file_path"]), config)
        if not resolved.exists():
            continue
        duration = audio_duration_seconds(resolved)
        if duration is not None and duration >= threshold:
            keep.append(idx)
    return df.loc[keep].copy()


def read_protocol_csv(
    csv_path: Path,
    *,
    datasets: list[str] | None = None,
    subsets: list[str] | None = None,
    status: str = "ok",
) -> pd.DataFrame:
    df = pd.read_csv(csv_path, low_memory=False)
    if status:
        df = df[df["status"].fillna("").eq(status)].copy()
    if datasets:
        df = df[df["dataset"].isin(datasets)].copy()
    if subsets:
        df = df[df["subset"].isin(subsets)].copy()
    df["generator"] = df.apply(lambda row: infer_generator(row.to_dict()), axis=1)
    df["y_spoof"] = df["label"].map(label_to_y_spoof).astype(int)
    return df


def protocol_summary(csv_path: Path) -> pd.DataFrame:
    df = read_protocol_csv(csv_path)
    grouped = (
        df.groupby(["dataset", "subset", "label"], dropna=False)
        .size()
        .reset_index(name="count")
        .sort_values(["dataset", "subset", "label"])
    )
    return grouped


def sample_with_replacement(pool: pd.DataFrame, n: int, rng: random.Random) -> pd.DataFrame:
    if pool.empty:
        raise RuntimeError("Pool vazio")
    if len(pool) >= n:
        indices = pool.index.to_list()
        rng.shuffle(indices)
        return pool.loc[indices[:n]].copy()
    return pool.sample(n=n, replace=True, random_state=rng.randint(0, 2**31 - 1)).copy()


def bonafide_pool_for(dataset: str, generator: str, df: pd.DataFrame) -> pd.DataFrame:
    ds = df[df["dataset"].eq(dataset)]
    if dataset in BONAFIDE_POOL_DATASET:
        return ds[ds["label"].astype(str).str.lower().eq("bonafide")].copy()
    pool_gen = BONAFIDE_POOL_GENERATOR.get(dataset)
    if pool_gen:
        return ds[ds["generator"].eq(pool_gen) & ds["label"].astype(str).str.lower().eq("bonafide")].copy()
    return ds[
        (ds["generator"].eq(generator) | ds["subset"].astype(str).eq(generator))
        & ds["label"].astype(str).str.lower().eq("bonafide")
    ].copy()


def spoof_pool_for(dataset: str, generator: str, df: pd.DataFrame) -> pd.DataFrame:
    ds = df[df["dataset"].eq(dataset)]
    return ds[
        (ds["generator"].eq(generator) | ds["subset"].astype(str).eq(generator))
        & ds["label"].astype(str).str.lower().eq("spoof")
    ].copy()


def sample_generator_balanced(
    df: pd.DataFrame,
    *,
    dataset: str,
    generator: str,
    per_class: int,
    seed: int,
) -> pd.DataFrame:
    rng = random.Random(seed)
    bonafide = sample_with_replacement(bonafide_pool_for(dataset, generator, df), per_class, rng)
    spoof = sample_with_replacement(spoof_pool_for(dataset, generator, df), per_class, rng)
    bonafide = bonafide.copy()
    spoof = spoof.copy()
    bonafide["sample_generator"] = generator
    spoof["sample_generator"] = generator
    return pd.concat([bonafide, spoof], ignore_index=True)


def sample_balanced(
    df: pd.DataFrame,
    *,
    per_class: int,
    seed: int,
    group_cols: tuple[str, ...] = ("dataset", "generator"),
) -> pd.DataFrame:
    rng = random.Random(seed)
    parts: list[pd.DataFrame] = []
    for key, group in df.groupby(list(group_cols), dropna=False):
        context = "/".join(str(part) for part in (key if isinstance(key, tuple) else (key,)))
        for y_spoof, label_name in ((0, "bonafide"), (1, "spoof")):
            pool = group[group["y_spoof"].eq(y_spoof)].copy()
            if len(pool) < per_class:
                raise RuntimeError(
                    f"Pool insuficiente para {context}/{label_name}: "
                    f"precisa {per_class}, disponível {len(pool)}"
                )
            indices = pool.index.to_list()
            rng.shuffle(indices)
            parts.append(pool.loc[indices[:per_class]])
    return pd.concat(parts, ignore_index=True).sample(frac=1.0, random_state=seed).reset_index(drop=True)


def assign_purpose_splits(
    df: pd.DataFrame,
    *,
    train_per_class: int,
    calib_per_class: int,
    test_per_class: int,
    seed: int,
    group_cols: tuple[str, ...] = ("dataset", "generator"),
) -> pd.DataFrame:
    total_per_class = train_per_class + calib_per_class + test_per_class
    if total_per_class <= 0:
        raise ValueError("Splits devem somar > 0")
    rng = random.Random(seed)
    rows: list[dict[str, Any]] = []
    for key, group in df.groupby(list(group_cols), dropna=False):
        for y_spoof, label_name in ((0, "bonafide"), (1, "spoof")):
            pool = group[group["y_spoof"].eq(y_spoof)].copy()
            if len(pool) < total_per_class:
                raise RuntimeError(
                    f"Split insuficiente para {key}/{label_name}: "
                    f"precisa {total_per_class}, disponível {len(pool)}"
                )
            indices = pool.index.to_list()
            rng.shuffle(indices)
            selected = pool.loc[indices[:total_per_class]].copy()
            selected = selected.sample(frac=1.0, random_state=seed + y_spoof).reset_index(drop=True)
            for idx, purpose in enumerate(
                ["calibration_train"] * train_per_class
                + ["calibration_bigauss"] * calib_per_class
                + ["evaluation"] * test_per_class
            ):
                row = selected.iloc[idx].to_dict()
                row["purpose"] = purpose
                row["reference_split"] = purpose
                row["label_name"] = label_name
                rows.append(row)
    out = pd.DataFrame(rows)
    return out.sample(frac=1.0, random_state=seed).reset_index(drop=True)


def reset_dir(path: Path, force: bool) -> None:
    if path.exists() and force:
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def write_manifest(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "purpose",
        "reference_split",
        "dataset",
        "generator",
        "subset",
        "label",
        "label_name",
        "y_spoof",
        "source_id",
        "source_path",
        "resolved_path",
        "dest_relative",
        "sha256",
        "bytes",
        "sync_status",
        "augmentation",
        "augmentation_params",
        "source_sha256",
        "parent_source_id",
    ]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")


def read_manifest(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    for row in rows:
        row["_manifest"] = str(path)
        row["_root"] = str(path.parent)
    return rows


def manifest_input_path(row: dict[str, str]) -> Path:
    dest = row.get("dest_relative")
    if dest:
        candidate = Path(row["_root"]) / dest
        if candidate.exists():
            return candidate
    resolved = row.get("resolved_path") or row.get("source_path")
    if not resolved:
        raise RuntimeError("Manifest row missing resolved_path/source_path")
    return Path(resolved)


def build_manifest_rows(
    sampled: pd.DataFrame,
    config: dict[str, Any],
    *,
    copy_files: bool,
    out_dir: Path,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for idx, record in sampled.iterrows():
        source_path = str(record["file_path"])
        resolved = resolve_audio_path(source_path, config)
        generator = str(record.get("generator") or infer_generator(record.to_dict()))
        label_name = str(record.get("label_name") or record["label"])
        y_spoof = int(record.get("y_spoof", label_to_y_spoof(str(record["label"]))))
        purpose = str(record.get("purpose", "calibration_train"))
        source_id = Path(source_path).stem
        dest_relative = ""
        digest = ""
        size = 0
        sync_status = "reference_only"

        if copy_files:
            if not resolved.exists():
                sync_status = "missing"
            else:
                suffix = resolved.suffix.lower() or ".wav"
                digest = sha256_file(resolved)
                filename = f"{safe_name(source_id)}__{digest[:12]}{suffix}"
                dest_relative = (
                    Path(purpose)
                    / safe_name(str(record["dataset"]))
                    / safe_name(generator)
                    / safe_name(label_name)
                    / filename
                ).as_posix()
                dest = out_dir / dest_relative
                dest.parent.mkdir(parents=True, exist_ok=True)
                if not dest.exists():
                    shutil.copy2(resolved, dest)
                size = dest.stat().st_size
                sync_status = "copied"

        rows.append(
            {
                "purpose": purpose,
                "reference_split": str(record.get("reference_split", purpose)),
                "dataset": str(record["dataset"]),
                "generator": generator,
                "subset": str(record.get("subset", "")),
                "label": str(record["label"]),
                "label_name": label_name,
                "y_spoof": y_spoof,
                "source_id": source_id,
                "source_path": source_path,
                "resolved_path": str(resolved),
                "dest_relative": dest_relative,
                "sha256": digest,
                "bytes": size,
                "sync_status": sync_status,
            }
        )
    return rows


def iter_accessible(rows: Iterable[dict[str, Any]], config: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    ok: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    for row in rows:
        resolved = resolve_audio_path(str(row.get("source_path", "")), config)
        row = dict(row)
        row["resolved_path"] = str(resolved)
        if resolved.exists():
            row["sync_status"] = "accessible"
            ok.append(row)
        else:
            row["sync_status"] = "missing"
            missing.append(row)
    return ok, missing
