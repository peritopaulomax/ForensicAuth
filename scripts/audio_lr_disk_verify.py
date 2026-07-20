"""Shared disk-only verification for audio LR reference completion."""

from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from audio_lr_dataset_utils import safe_name
from core.audio_spoofing_lr_reference import REFERENCE_GENERATORS
from core.latent_typicality.representations_utils import (
    ORIGINAL_AUGMENTATION_TAG,
    build_sample_id,
    source_id_stem,
)

DETECTORS = ("df_arena_1b", "sls_xlsr", "wedefense_wavlm_mhfa")
AUGMENTATIONS = ("mp3_128k", "opus_32k", "noise_snr_20", "noise_snr_15")
LABELS = ("bonafide", "spoof")
TARGET_PER_CLASS = 500
TARGET_AUG_PER_CLASS = TARGET_PER_CLASS * len(AUGMENTATIONS)
UNITS_PER_ELIGIBLE_GENERATOR = (TARGET_PER_CLASS * 2) * (1 + len(AUGMENTATIONS))


@dataclass
class Bucket:
    wav: int = 0
    emb_complete: int = 0
    emb_partial: int = 0
    scores: int = 0
    complete_units: int = 0


@dataclass
class SubgroupAudit:
    dataset: str
    generator: str
    eligible_500: bool = True
    target_bf_orig: int = TARGET_PER_CLASS
    target_sp_orig: int = TARGET_PER_CLASS
    target_bf_aug: int = TARGET_AUG_PER_CLASS
    target_sp_aug: int = TARGET_AUG_PER_CLASS
    target_units: int = UNITS_PER_ELIGIBLE_GENERATOR
    orig_bonafide: Bucket = field(default_factory=Bucket)
    orig_spoof: Bucket = field(default_factory=Bucket)
    aug_bonafide: Bucket = field(default_factory=Bucket)
    aug_spoof: Bucket = field(default_factory=Bucket)
    orig_audio_missing: int = 0
    orig_score_rows: int = 0
    gaps: list[dict[str, Any]] = field(default_factory=list)

    @property
    def units_ok(self) -> int:
        return (
            self.orig_bonafide.complete_units
            + self.orig_spoof.complete_units
            + self.aug_bonafide.complete_units
            + self.aug_spoof.complete_units
        )

    @property
    def pct(self) -> float:
        if self.target_units <= 0:
            return 100.0
        return round(100.0 * self.units_ok / self.target_units, 2)

    @property
    def passed(self) -> bool:
        return self.units_ok >= self.target_units and not self.gaps


def scores_sidecar_path(embed_dir: Path, sample_id: str) -> Path:
    return embed_dir / f"{sample_id}.scores.json"


def write_scores_sidecar(embed_dir: Path, sample_id: str, out_row: dict[str, Any]) -> Path:
    payload: dict[str, Any] = {"sample_id": sample_id, "detectors": {}}
    for det in DETECTORS:
        payload["detectors"][det] = {
            "bonafide_logit": out_row.get(f"{det}_bonafide_logit"),
            "spoof_logit": out_row.get(f"{det}_spoof_logit"),
            "bonafide_prob": out_row.get(f"{det}_bonafide_prob"),
        }
    path = scores_sidecar_path(embed_dir, sample_id)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def read_scores_sidecar(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    detectors = data.get("detectors") or {}
    for det in DETECTORS:
        block = detectors.get(det) or {}
        if block.get("bonafide_logit") in (None, "") or block.get("spoof_logit") in (None, ""):
            return False
    return True


def _parse_aug_wav(path: Path, ref_root: Path) -> tuple[str, str, str, str, str] | None:
    try:
        rel = path.relative_to(ref_root)
    except ValueError:
        return None
    parts = rel.parts
    if len(parts) != 6 or parts[2] not in LABELS or parts[3] != "augmented":
        return None
    dataset, generator, label, _, aug, _ = parts
    if aug not in AUGMENTATIONS:
        return None
    stem = path.stem
    m = re.match(r"^(.+)__(mp3_128k|opus_32k|noise_snr_20|noise_snr_15)__[0-9a-f]{12}$", stem)
    if not m:
        return None
    return dataset, generator, label, aug, m.group(1)


def _parse_npy(path: Path) -> tuple[str, str] | None:
    name = path.stem
    for det in DETECTORS:
        suffix = f"__{det}"
        if name.endswith(suffix):
            return name[: -len(suffix)], det
    return None


def _has_scores_row(row: dict) -> bool:
    for det in DETECTORS:
        val = row.get(f"{det}_bonafide_logit")
        if val is None or (isinstance(val, float) and pd.isna(val)) or val == "":
            return False
    return True


def _emb_complete(sample_id: str, emb_index: dict[str, set[str]], embed_dir: Path) -> bool:
    dets = emb_index.get(sample_id, set())
    if len(dets) != len(DETECTORS):
        return False
    for det in DETECTORS:
        npy = embed_dir / f"{sample_id}__{det}.npy"
        if not npy.is_file():
            return False
    return True


def _score_complete(
    sample_id: str,
    embed_dir: Path,
    *,
    csv_row: dict | None = None,
) -> bool:
    sidecar = scores_sidecar_path(embed_dir, sample_id)
    if read_scores_sidecar(sidecar):
        return True
    return bool(csv_row and _has_scores_row(csv_row))


def _count_complete(sample_ids: set[str], emb_index: dict[str, set[str]], embed_dir: Path, score_lookup: dict[str, dict]) -> int:
    n = 0
    for sid in sample_ids:
        if not _emb_complete(sid, emb_index, embed_dir):
            continue
        if not _score_complete(sid, embed_dir, csv_row=score_lookup.get(sid)):
            continue
        n += 1
    return n


def scan_augmented_wavs(ref_root: Path) -> dict[tuple[str, str, str], set[str]]:
    out: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    if not ref_root.is_dir():
        return out
    for dirpath, _, filenames in os.walk(ref_root):
        for fn in filenames:
            if not fn.endswith(".wav"):
                continue
            p = Path(dirpath) / fn
            if not p.is_file():
                continue
            parsed = _parse_aug_wav(p, ref_root)
            if not parsed:
                continue
            dataset, generator, label, aug, parent_stem = parsed
            sid = build_sample_id(
                dataset=dataset,
                generator=generator,
                source_id=parent_stem,
                augmentation=aug,
            )
            out[(dataset, generator, label)].add(sid)
    return out


def scan_embeddings(emb_dir: Path) -> dict[str, set[str]]:
    out: dict[str, set[str]] = defaultdict(set)
    if not emb_dir.is_dir():
        return out
    for dirpath, _, filenames in os.walk(emb_dir):
        for fn in filenames:
            if not fn.endswith(".npy"):
                continue
            p = Path(dirpath) / fn
            if not p.is_file():
                continue
            parsed = _parse_npy(p)
            if not parsed:
                continue
            sample_id, det = parsed
            out[sample_id].add(det)
    return out


def load_aug_score_index(path: Path) -> dict[str, dict]:
    if not path.is_file():
        return {}
    cols = ["sample_id"] + [f"{d}_bonafide_logit" for d in DETECTORS]
    df = pd.read_csv(path, usecols=lambda c: c in cols or c == "error", low_memory=False)
    if "error" in df.columns:
        df = df[df["error"].fillna("").eq("")]
    return {str(r["sample_id"]): r for r in df.to_dict(orient="records") if r.get("sample_id")}


def load_eligibility(protocol_audit_csv: Path) -> dict[tuple[str, str], dict[str, Any]]:
    if not protocol_audit_csv.is_file():
        return {}
    df = pd.read_csv(protocol_audit_csv)
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for rec in df.to_dict(orient="records"):
        key = (str(rec["dataset"]), str(rec["generator"]))
        out[key] = rec
    return out


def _apply_eligibility(audit: SubgroupAudit, elig: dict[str, Any] | None) -> None:
    if not elig:
        return
    audit.eligible_500 = bool(elig.get("eligible_500", True))
    if "target_bf_orig" in elig and "target_sp_orig" in elig:
        audit.target_bf_orig = int(elig["target_bf_orig"])
        audit.target_sp_orig = int(elig["target_sp_orig"])
    else:
        bf = int(elig.get("bf_unique", TARGET_PER_CLASS) or 0)
        sp = int(elig.get("sp_unique", TARGET_PER_CLASS) or 0)
        audit.target_bf_orig = TARGET_PER_CLASS if audit.eligible_500 else min(TARGET_PER_CLASS, bf)
        audit.target_sp_orig = TARGET_PER_CLASS if audit.eligible_500 else min(TARGET_PER_CLASS, sp)
    audit.target_bf_aug = audit.target_bf_orig * len(AUGMENTATIONS)
    audit.target_sp_aug = audit.target_sp_orig * len(AUGMENTATIONS)
    audit.target_units = (
        audit.target_bf_orig + audit.target_sp_orig + audit.target_bf_aug + audit.target_sp_aug
    )


def _record_gaps(audit: SubgroupAudit) -> None:
    audit.gaps = []
    checks = [
        ("bf_orig", audit.orig_bonafide, audit.target_bf_orig),
        ("sp_orig", audit.orig_spoof, audit.target_sp_orig),
        ("bf_aug", audit.aug_bonafide, audit.target_bf_aug),
        ("sp_aug", audit.aug_spoof, audit.target_sp_aug),
    ]
    for name, bucket, target in checks:
        if bucket.wav < target:
            audit.gaps.append({"field": f"{name}_wav", "have": bucket.wav, "need": target})
        if bucket.emb_complete < min(bucket.wav, target):
            audit.gaps.append({"field": f"{name}_emb_3of3", "have": bucket.emb_complete, "need": min(bucket.wav, target)})
        if bucket.scores < min(bucket.wav, target):
            audit.gaps.append({"field": f"{name}_scores", "have": bucket.scores, "need": min(bucket.wav, target)})
        if bucket.complete_units < target:
            audit.gaps.append({"field": f"{name}_complete_units", "have": bucket.complete_units, "need": target})


def audit_originals(
    audits: dict[tuple[str, str], SubgroupAudit],
    score_matrix: Path,
    orig_emb: dict[str, set[str]],
    orig_emb_dir: Path,
    orig_score_lookup: dict[str, dict],
) -> None:
    if not score_matrix.is_file():
        return
    df = pd.read_csv(score_matrix, low_memory=False)
    if "error" in df.columns:
        df = df[df["error"].fillna("").eq("")]

    seen: dict[tuple[str, str, str], set[str]] = defaultdict(set)

    for rec in df.to_dict(orient="records"):
        dataset = str(rec.get("dataset") or "")
        generator = str(rec.get("generator") or "")
        if (dataset, generator) not in audits:
            continue
        label = str(rec.get("label") or "").lower()
        if label not in LABELS:
            continue
        audit = audits[(dataset, generator)]
        audit.orig_score_rows += 1

        source_id = str(rec.get("source_id") or "")
        sid = build_sample_id(
            dataset=dataset,
            generator=generator,
            source_id=source_id_stem(source_id),
            augmentation=ORIGINAL_AUGMENTATION_TAG,
        )
        key = (dataset, generator, label)
        if sid in seen[key]:
            continue
        seen[key].add(sid)

        audio_path = str(rec.get("audio_path") or "")
        audio_ok = bool(audio_path) and Path(audio_path).is_file()
        bucket = audit.orig_bonafide if label == "bonafide" else audit.orig_spoof
        if audio_ok:
            bucket.wav += 1
        else:
            audit.orig_audio_missing += 1

        if _emb_complete(sid, orig_emb, orig_emb_dir):
            bucket.emb_complete += 1
        elif orig_emb.get(sid):
            bucket.emb_partial += 1

        if audio_ok and _score_complete(sid, orig_emb_dir, csv_row=rec):
            bucket.scores += 1

        if audio_ok and _emb_complete(sid, orig_emb, orig_emb_dir) and _score_complete(sid, orig_emb_dir, csv_row=rec):
            bucket.complete_units += 1


def _aug_wav_on_disk(ref_root: Path, dataset: str, generator: str, label: str, source_stem: str, aug: str) -> bool:
    """Match augmentation WAV by the same safe_name convention used to write it.

    Critical: filenames are written with ``safe_name(source_id)`` which strips
    trailing underscores, so we glob by ``safe_name(source_stem)`` rather than
    re-deriving a sample_id from the filename (which would be lossy for source ids
    ending in '_').
    """
    aug_dir = ref_root / safe_name(dataset) / safe_name(generator) / safe_name(label) / "augmented" / safe_name(aug)
    if not aug_dir.is_dir():
        return False
    pattern = f"{safe_name(source_stem)}__{safe_name(aug)}__*.wav"
    return any(aug_dir.glob(pattern))


def audit_augmented_from_matrix(
    audits: dict[tuple[str, str], SubgroupAudit],
    score_matrix: Path,
    ref_root: Path,
    aug_emb: dict[str, set[str]],
    aug_emb_dir: Path,
    aug_scores: dict[str, dict],
) -> None:
    """Count augmentation completeness driven by the frozen matrix source ids.

    This is authoritative: for each unique original source id we expect exactly the
    4 augmentations, and check WAV + 3 embeddings + score for each. It avoids parsing
    WAV filenames (which is lossy for ids ending in '_') and ignores stray files.
    """
    if not score_matrix.is_file():
        return
    df = pd.read_csv(score_matrix, low_memory=False)
    if "error" in df.columns:
        df = df[df["error"].fillna("").eq("")]

    seen: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for rec in df.to_dict(orient="records"):
        dataset = str(rec.get("dataset") or "")
        generator = str(rec.get("generator") or "")
        if (dataset, generator) not in audits:
            continue
        label = str(rec.get("label") or "").lower()
        if label not in LABELS:
            continue
        stem = source_id_stem(str(rec.get("source_id") or ""))
        key = (dataset, generator, label)
        if stem in seen[key]:
            continue
        seen[key].add(stem)

        audit = audits[(dataset, generator)]
        bucket = audit.aug_bonafide if label == "bonafide" else audit.aug_spoof
        for aug in AUGMENTATIONS:
            sample_id = build_sample_id(dataset=dataset, generator=generator, source_id=stem, augmentation=aug)
            wav_ok = _aug_wav_on_disk(ref_root, dataset, generator, label, stem, aug)
            emb_ok = _emb_complete(sample_id, aug_emb, aug_emb_dir)
            score_ok = _score_complete(sample_id, aug_emb_dir, csv_row=aug_scores.get(sample_id))
            if wav_ok:
                bucket.wav += 1
            if emb_ok:
                bucket.emb_complete += 1
            elif aug_emb.get(sample_id):
                bucket.emb_partial += 1
            if score_ok:
                bucket.scores += 1
            if wav_ok and emb_ok and score_ok:
                bucket.complete_units += 1


def fill_augmented_buckets(
    audits: dict[tuple[str, str], SubgroupAudit],
    aug_wavs: dict[tuple[str, str, str], set[str]],
    aug_emb: dict[str, set[str]],
    aug_emb_dir: Path,
    aug_scores: dict[str, dict],
) -> None:
    for (dataset, generator, label), sample_ids in aug_wavs.items():
        if (dataset, generator) not in audits:
            continue
        audit = audits[(dataset, generator)]
        bucket = audit.aug_bonafide if label == "bonafide" else audit.aug_spoof
        bucket.wav = len(sample_ids)
        for sid in sample_ids:
            if _emb_complete(sid, aug_emb, aug_emb_dir):
                bucket.emb_complete += 1
            elif aug_emb.get(sid):
                bucket.emb_partial += 1
            if _score_complete(sid, aug_emb_dir, csv_row=aug_scores.get(sid)):
                bucket.scores += 1
            if (
                _emb_complete(sid, aug_emb, aug_emb_dir)
                and _score_complete(sid, aug_emb_dir, csv_row=aug_scores.get(sid))
            ):
                bucket.complete_units += 1


def run_disk_audit(
    *,
    base_dir: Path,
    protocol_audit_csv: Path | None = None,
) -> tuple[list[SubgroupAudit], dict[str, Any]]:
    ref_root = base_dir / "samples/augmented/reference_population"
    orig_emb_dir = base_dir / "representations/originals/embeddings"
    aug_emb_dir = base_dir / "representations/augmented/embeddings"
    score_matrix = base_dir / "score_matrices/lr_scores_balanced_full.csv"
    aug_repr = base_dir / "representations/augmented/representations.csv"
    eligibility = load_eligibility(protocol_audit_csv or Path())

    audits: dict[tuple[str, str], SubgroupAudit] = {}
    for dataset, generators in REFERENCE_GENERATORS.items():
        for generator in generators:
            audit = SubgroupAudit(dataset=dataset, generator=generator)
            _apply_eligibility(audit, eligibility.get((dataset, generator)))
            audits[(dataset, generator)] = audit

    orig_emb = scan_embeddings(orig_emb_dir)
    aug_emb = scan_embeddings(aug_emb_dir)
    aug_scores = load_aug_score_index(aug_repr)

    audit_originals(audits, score_matrix, orig_emb, orig_emb_dir, {})
    audit_augmented_from_matrix(audits, score_matrix, ref_root, aug_emb, aug_emb_dir, aug_scores)

    audit_list = sorted(audits.values(), key=lambda a: (a.dataset, a.generator))
    for audit in audit_list:
        _record_gaps(audit)

    eligible = [a for a in audit_list if a.eligible_500]
    ineligible = [a for a in audit_list if not a.eligible_500]
    units_ok = sum(a.units_ok for a in audit_list)
    units_target = sum(a.target_units for a in audit_list)
    eligible_ok = sum(a.units_ok for a in eligible)
    eligible_target = sum(a.target_units for a in eligible)

    summary: dict[str, Any] = {
        "target_per_eligible_generator": UNITS_PER_ELIGIBLE_GENERATOR,
        "eligible_generators": len(eligible),
        "ineligible_generators": [f"{a.dataset}/{a.generator}" for a in ineligible],
        "global_units_ok": units_ok,
        "global_units_target": units_target,
        "global_pct": round(100.0 * units_ok / units_target, 2) if units_target else 0.0,
        "eligible_units_ok": eligible_ok,
        "eligible_units_target": eligible_target,
        "eligible_pct": round(100.0 * eligible_ok / eligible_target, 2) if eligible_target else 0.0,
        "passed": all(a.passed for a in audit_list),
        "eligible_passed": all(a.passed for a in eligible) if eligible else True,
    }
    return audit_list, summary


def audit_to_row(a: SubgroupAudit) -> dict[str, Any]:
    def b(bucket: Bucket, prefix: str) -> dict[str, Any]:
        return {
            f"{prefix}_wav_disk": bucket.wav,
            f"{prefix}_emb_3of3": bucket.emb_complete,
            f"{prefix}_emb_partial": bucket.emb_partial,
            f"{prefix}_scores": bucket.scores,
            f"{prefix}_complete_units": bucket.complete_units,
        }

    row: dict[str, Any] = {
        "dataset": a.dataset,
        "generator": a.generator,
        "eligible_500": a.eligible_500,
        "target_units": a.target_units,
        "units_ok": a.units_ok,
        "pct": a.pct,
        "passed": a.passed,
        "orig_score_matrix_rows": a.orig_score_rows,
        "orig_audio_missing_on_disk": a.orig_audio_missing,
        "target_bf_orig": a.target_bf_orig,
        "target_sp_orig": a.target_sp_orig,
        "target_bf_aug": a.target_bf_aug,
        "target_sp_aug": a.target_sp_aug,
        "gaps_json": json.dumps(a.gaps, ensure_ascii=False),
    }
    row.update(b(a.orig_bonafide, "bf_orig"))
    row.update(b(a.orig_spoof, "sp_orig"))
    row.update(b(a.aug_bonafide, "bf_aug"))
    row.update(b(a.aug_spoof, "sp_aug"))
    return row
