#!/usr/bin/env python3
"""Consolidated inventory of the audio spoofing LR reference bases.

For every subgroup (dataset/generator) reports, per class (bonafide/spoof):
- unique original source ids with complete finite scores,
- NaN-logit rows and duplicate rows in the score matrix,
- augmentation WAVs and their embeddings,
- whether originals and augmentations have 3 embeddings + score sidecar/score.

Outputs a CSV and a human-readable table. Read-only: touches no data files.
"""

from __future__ import annotations

import argparse
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src" / "backend"))

from audio_lr_disk_verify import (  # noqa: E402
    AUGMENTATIONS,
    DETECTORS,
    LABELS,
    load_aug_score_index,
    run_disk_audit,
)
from core.latent_typicality.representations_utils import source_id_stem  # noqa: E402

LOGIT_COLS = [f"{det}_bonafide_logit" for det in DETECTORS]


def _finite(v: Any) -> bool:
    try:
        return math.isfinite(float(v))
    except (TypeError, ValueError):
        return False


def _blank(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, float) and math.isnan(v):
        return True
    t = str(v).strip().lower()
    return t == "" or t == "nan"


def matrix_stats(score_matrix: Path) -> dict[tuple[str, str, str], dict[str, int]]:
    """Per (dataset, generator, label): score rows, NaN rows, duplicate rows, unique complete ids."""
    out: dict[tuple[str, str, str], dict[str, int]] = defaultdict(
        lambda: {"score_rows": 0, "nan_rows": 0, "error_rows": 0, "dup_rows": 0, "unique_complete": 0}
    )
    if not score_matrix.is_file():
        return out
    df = pd.read_csv(score_matrix, low_memory=False)

    seen: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    dup_seen: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for rec in df.to_dict(orient="records"):
        label = str(rec.get("label", "")).strip().lower()
        if label not in LABELS:
            continue
        key = (str(rec.get("dataset", "")), str(rec.get("generator", "")), label)
        bucket = out[key]
        is_error = not _blank(rec.get("error"))
        if is_error:
            bucket["error_rows"] += 1
            continue
        bucket["score_rows"] += 1
        finite = all(_finite(rec.get(c)) for c in LOGIT_COLS)
        if not finite:
            bucket["nan_rows"] += 1
        sid = source_id_stem(str(rec.get("source_id", "")))
        if sid in dup_seen[key]:
            bucket["dup_rows"] += 1
        else:
            dup_seen[key].add(sid)
        if finite and sid not in seen[key]:
            seen[key].add(sid)
            bucket["unique_complete"] += 1
    return out


def build_inventory(base_dir: Path, protocol_audit: Path) -> pd.DataFrame:
    score_matrix = base_dir / "score_matrices/lr_scores_balanced_full.csv"
    audits, _ = run_disk_audit(base_dir=base_dir, protocol_audit_csv=protocol_audit)
    mstats = matrix_stats(score_matrix)

    rows: list[dict[str, Any]] = []
    for a in audits:
        for label, mkey, ob, ab, t_orig, t_aug in (
            ("bonafide", "bonafide", a.orig_bonafide, a.aug_bonafide, a.target_bf_orig, a.target_bf_aug),
            ("spoof", "spoof", a.orig_spoof, a.aug_spoof, a.target_sp_orig, a.target_sp_aug),
        ):
            ms = mstats.get((a.dataset, a.generator, mkey), {})
            rows.append(
                {
                    "dataset": a.dataset,
                    "generator": a.generator,
                    "classe": label,
                    "alvo_orig": t_orig,
                    "orig_scores_unicos": ms.get("unique_complete", 0),
                    "orig_wav_disco": ob.wav,
                    "orig_emb_3de3": ob.emb_complete,
                    "orig_score_ok": ob.scores,
                    "orig_completos": ob.complete_units,
                    "alvo_aug": t_aug,
                    "aug_wav_disco": ab.wav,
                    "aug_emb_3de3": ab.emb_complete,
                    "aug_score_ok": ab.scores,
                    "aug_completos": ab.complete_units,
                    "nan_linhas": ms.get("nan_rows", 0),
                    "duplicatas": ms.get("dup_rows", 0),
                    "erro_linhas": ms.get("error_rows", 0),
                    "orig_ok": ob.complete_units >= t_orig,
                    "aug_ok": ab.complete_units >= t_aug,
                }
            )
    return pd.DataFrame(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-dir", default="outputs/lr_calibration/audio_spoofing")
    parser.add_argument(
        "--protocol-audit",
        default="outputs/lr_calibration/audio_spoofing/inventory/effective_pool_audit.csv",
    )
    parser.add_argument("--out", default="outputs/lr_calibration/audio_spoofing/inventory/bases_inventory.csv")
    args = parser.parse_args()

    base_dir = ROOT / args.base_dir
    protocol_audit = ROOT / args.protocol_audit
    if not protocol_audit.is_file():
        protocol_audit = base_dir / "inventory/protocol_pool_audit.csv"

    df = build_inventory(base_dir, protocol_audit)
    out_path = ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)

    # Console report
    pd.set_option("display.max_rows", None)
    pd.set_option("display.width", 200)
    show = df[[
        "dataset", "generator", "classe", "orig_completos", "alvo_orig",
        "aug_completos", "alvo_aug", "nan_linhas", "duplicatas", "erro_linhas", "orig_ok", "aug_ok",
    ]]
    print(show.to_string(index=False))

    totals = {
        "subgrupos": df[["dataset", "generator"]].drop_duplicates().shape[0],
        "orig_bonafide": int(df[df.classe.eq("bonafide")]["orig_completos"].sum()),
        "orig_spoof": int(df[df.classe.eq("spoof")]["orig_completos"].sum()),
        "aug_bonafide": int(df[df.classe.eq("bonafide")]["aug_completos"].sum()),
        "aug_spoof": int(df[df.classe.eq("spoof")]["aug_completos"].sum()),
        "total_nan": int(df["nan_linhas"].sum()),
        "total_duplicatas": int(df["duplicatas"].sum()),
        "total_erro": int(df["erro_linhas"].sum()),
        "grupos_orig_incompletos": int((~df["orig_ok"]).sum()),
        "grupos_aug_incompletos": int((~df["aug_ok"]).sum()),
    }
    print("\n=== TOTAIS ===")
    for k, v in totals.items():
        print(f"  {k}: {v}")
    print(f"\nCSV: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
