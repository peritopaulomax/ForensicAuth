#!/usr/bin/env python3
"""Build a frozen selection lock for the audio LR reference population.

For every (dataset, generator, label) it pins EXACTLY the target number of unique
source_ids (500, or the real protocol ceiling for spoof-limited SONAR generators):

1. Keep source_ids already scored on disk (from the sanitized score matrix).
2. Fill the remainder from the protocol pool, preferring source_ids that were
   previously attempted but failed scoring (the NaN worklist), then fresh ones.

Outputs:
- selection_lock.csv  : the pinned set (needs_scoring flag per row)
- score_manifest.csv  : subset that still needs detector scoring (manifest format)
- selection_lock_report.json : per-group kept/new/target/shortfall

Deterministic and idempotent: rerunning after scoring shrinks the manifest to 0.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src" / "backend"))

from audio_lr_dataset_utils import (  # noqa: E402
    bonafide_pool_for,
    infer_generator,
    label_to_y_spoof,
    load_config,
    resolve_audio_path,
    spoof_pool_for,
)
from core.audio_spoofing_lr_reference import REFERENCE_GENERATORS  # noqa: E402
from core.latent_typicality.representations_utils import source_id_stem  # noqa: E402

LABELS = ("bonafide", "spoof")


def _load_protocol(protocol_csv: Path, cache_path: Path, datasets: set[str]) -> pd.DataFrame:
    if cache_path.is_file():
        df = pd.read_pickle(cache_path)
        return df[df["dataset"].isin(datasets)].copy()
    chunks: list[pd.DataFrame] = []
    for chunk in pd.read_csv(protocol_csv, chunksize=200_000, low_memory=False):
        chunk = chunk[chunk["status"].fillna("").eq("ok")].copy()
        chunk = chunk[chunk["dataset"].isin(datasets)].copy()
        if chunk.empty:
            continue
        chunk["generator"] = chunk.apply(lambda row: infer_generator(row.to_dict()), axis=1)
        chunk["y_spoof"] = chunk["label"].map(label_to_y_spoof).astype(int)
        chunks.append(chunk)
    return pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame()


def _targets_from_audit(audit_csv: Path) -> dict[tuple[str, str, str], int]:
    targets: dict[tuple[str, str, str], int] = {}
    audit = pd.read_csv(audit_csv)
    for _, r in audit.iterrows():
        targets[(str(r["dataset"]), str(r["generator"]), "bonafide")] = int(r["target_bf_orig"])
        targets[(str(r["dataset"]), str(r["generator"]), "spoof")] = int(r["target_sp_orig"])
    return targets


def _kept_from_matrix(score_matrix: Path) -> dict[tuple[str, str, str], list[dict[str, Any]]]:
    df = pd.read_csv(score_matrix, low_memory=False)
    if "error" in df.columns:
        df = df[df["error"].isna() | df["error"].astype(str).str.strip().isin(["", "nan"])].copy()
    kept: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    seen: dict[tuple[str, str, str], set[str]] = {}
    for rec in df.to_dict(orient="records"):
        label = str(rec.get("label", "")).strip().lower()
        key = (str(rec.get("dataset", "")), str(rec.get("generator", "")), label)
        sid = source_id_stem(str(rec.get("source_id", "")))
        audio = str(rec.get("audio_path") or "")
        if not sid or not audio or not Path(audio).is_file():
            continue
        seen.setdefault(key, set())
        if sid in seen[key]:
            continue
        seen[key].add(sid)
        kept.setdefault(key, []).append({"source_id": sid, "audio_path": audio})
    return kept


def _worklist_sids(worklist_csv: Path) -> dict[tuple[str, str, str], set[str]]:
    out: dict[tuple[str, str, str], set[str]] = {}
    if not worklist_csv.is_file():
        return out
    df = pd.read_csv(worklist_csv, low_memory=False)
    for rec in df.to_dict(orient="records"):
        label = str(rec.get("label", "")).strip().lower()
        key = (str(rec.get("dataset", "")), str(rec.get("generator", "")), label)
        sid = source_id_stem(str(rec.get("source_id", "")))
        if sid:
            out.setdefault(key, set()).add(sid)
    return out


def _unusable_sids(unusable_csv: Path) -> dict[tuple[str, str, str], set[str]]:
    """Source ids that failed scoring deterministically and must never be reselected."""
    out: dict[tuple[str, str, str], set[str]] = {}
    if not unusable_csv.is_file():
        return out
    df = pd.read_csv(unusable_csv, low_memory=False)
    for rec in df.to_dict(orient="records"):
        label = str(rec.get("label", "")).strip().lower()
        key = (str(rec.get("dataset", "")), str(rec.get("generator", "")), label)
        sid = source_id_stem(str(rec.get("source_id", "")))
        if sid:
            out.setdefault(key, set()).add(sid)
    return out


def build_lock(
    *,
    score_matrix: Path,
    protocol_csv: Path,
    cache_path: Path,
    audit_csv: Path,
    worklist_csv: Path,
    unusable_csv: Path,
    config: dict,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    targets = _targets_from_audit(audit_csv)
    kept = _kept_from_matrix(score_matrix)
    worklist = _worklist_sids(worklist_csv)
    unusable = _unusable_sids(unusable_csv)
    protocol = _load_protocol(protocol_csv, cache_path, set(REFERENCE_GENERATORS.keys()))

    selection_rows: list[dict[str, Any]] = []
    report: list[dict[str, Any]] = []

    for dataset, generators in REFERENCE_GENERATORS.items():
        for generator in generators:
            for label in LABELS:
                key = (dataset, generator, label)
                target = targets.get(key, 500)
                y_spoof = label_to_y_spoof(label)

                selected_sids: set[str] = set()
                kept_rows = kept.get(key, [])[:target]
                for kr in kept_rows:
                    selected_sids.add(kr["source_id"])
                    selection_rows.append(
                        {
                            "dataset": dataset,
                            "generator": generator,
                            "label": label,
                            "y_spoof": y_spoof,
                            "source_id": kr["source_id"],
                            "source_path": kr["audio_path"],
                            "resolved_path": kr["audio_path"],
                            "needs_scoring": False,
                        }
                    )

                need = target - len(kept_rows)
                new_added = 0
                if need > 0 and not protocol.empty:
                    pool = (
                        bonafide_pool_for(dataset, generator, protocol)
                        if label == "bonafide"
                        else spoof_pool_for(dataset, generator, protocol)
                    )
                    prefer = worklist.get(key, set())
                    bad = unusable.get(key, set())
                    candidates = pool.to_dict(orient="records")
                    # Deterministic order: preferred (previously attempted) first, then by source id.
                    def _sort_key(rec: dict[str, Any]) -> tuple[int, str]:
                        sid = source_id_stem(str(rec.get("source_id") or Path(str(rec.get("file_path") or "")).name))
                        return (0 if sid in prefer else 1, sid)

                    for rec in sorted(candidates, key=_sort_key):
                        if need <= 0:
                            break
                        file_path = str(rec.get("file_path") or "")
                        sid = source_id_stem(str(rec.get("source_id") or Path(file_path).name))
                        if not sid or sid in selected_sids or sid in bad:
                            continue
                        resolved = resolve_audio_path(file_path, config)
                        if not resolved.is_file():
                            continue
                        selected_sids.add(sid)
                        selection_rows.append(
                            {
                                "dataset": dataset,
                                "generator": generator,
                                "label": label,
                                "y_spoof": y_spoof,
                                "source_id": sid,
                                "source_path": file_path,
                                "resolved_path": str(resolved),
                                "needs_scoring": True,
                            }
                        )
                        new_added += 1
                        need -= 1

                final = len(kept_rows) + new_added
                report.append(
                    {
                        "dataset": dataset,
                        "generator": generator,
                        "label": label,
                        "target": target,
                        "kept": len(kept_rows),
                        "new_to_score": new_added,
                        "final": final,
                        "shortfall": max(0, target - final),
                    }
                )

    selection_df = pd.DataFrame(selection_rows)
    manifest_df = _to_manifest(selection_df[selection_df["needs_scoring"]]) if not selection_df.empty else pd.DataFrame()
    summary = {
        "total_selected": int(len(selection_df)),
        "total_to_score": int(selection_df["needs_scoring"].sum()) if not selection_df.empty else 0,
        "groups_with_shortfall": [r for r in report if r["shortfall"] > 0],
        "report": report,
    }
    return selection_df, manifest_df, summary


def _write_effective_targets(*, audit_csv: Path, report: list[dict[str, Any]], out_path: Path) -> None:
    """Reconcile the protocol pool audit targets with the frozen selection finals."""
    finals: dict[tuple[str, str], dict[str, int]] = {}
    for r in report:
        key = (str(r["dataset"]), str(r["generator"]))
        entry = finals.setdefault(key, {"bonafide": 0, "spoof": 0})
        entry[r["label"]] = int(r["final"])

    base = pd.read_csv(audit_csv) if audit_csv.is_file() else pd.DataFrame()
    rows: list[dict[str, Any]] = []
    base_by_key = {(str(r["dataset"]), str(r["generator"])): r for r in base.to_dict(orient="records")} if not base.empty else {}
    for key, fin in finals.items():
        rec = dict(base_by_key.get(key, {"dataset": key[0], "generator": key[1]}))
        rec["dataset"], rec["generator"] = key
        rec["target_bf_orig"] = fin["bonafide"]
        rec["target_sp_orig"] = fin["spoof"]
        # eligible_500 stays true only when both classes reach the full 500 target.
        rec["eligible_500"] = bool(fin["bonafide"] >= 500 and fin["spoof"] >= 500)
        rows.append(rec)
    pd.DataFrame(rows).to_csv(out_path, index=False)


def _to_manifest(sel: pd.DataFrame) -> pd.DataFrame:
    if sel.empty:
        return pd.DataFrame()
    rows = []
    for rec in sel.to_dict(orient="records"):
        label = rec["label"]
        rows.append(
            {
                "purpose": "reference_population",
                "reference_split": "reference_population",
                "dataset": rec["dataset"],
                "generator": rec["generator"],
                "subset": rec["generator"],
                "label": label,
                "label_name": label,
                "y_spoof": rec["y_spoof"],
                "source_id": rec["source_id"],
                "source_path": rec["source_path"],
                "resolved_path": rec["resolved_path"],
                "augmentation": "",
                "sha256": "",
                "parent_source_id": rec["source_id"],
            }
        )
    return pd.DataFrame(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/audio_lr_protocolo.yaml")
    parser.add_argument("--protocol-csv", default="protocolo_unificado.csv")
    parser.add_argument(
        "--score-matrix",
        default="outputs/lr_calibration/audio_spoofing/score_matrices/lr_scores_balanced_full.csv",
    )
    parser.add_argument(
        "--audit-csv",
        default="outputs/lr_calibration/audio_spoofing/inventory/protocol_pool_audit.csv",
    )
    parser.add_argument(
        "--out-dir",
        default="outputs/lr_calibration/audio_spoofing/inventory",
    )
    args = parser.parse_args()

    config = load_config(ROOT / args.config)
    score_matrix = ROOT / args.score_matrix
    out_dir = ROOT / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_path = out_dir / "protocol_reference_cache.pkl"
    worklist_csv = score_matrix.parent / "sanitize_nan_worklist.csv"
    unusable_csv = out_dir / "unusable_source_ids.csv"

    selection_df, manifest_df, summary = build_lock(
        score_matrix=score_matrix,
        protocol_csv=ROOT / args.protocol_csv,
        cache_path=cache_path,
        audit_csv=ROOT / args.audit_csv,
        worklist_csv=worklist_csv,
        unusable_csv=unusable_csv,
        config=config,
    )

    selection_path = out_dir / "selection_lock.csv"
    manifest_path = out_dir / "score_manifest.csv"
    report_path = out_dir / "selection_lock_report.json"

    selection_df.to_csv(selection_path, index=False)
    if not manifest_df.empty:
        manifest_df.to_csv(manifest_path, index=False)
    report_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    # Emit effective targets = the frozen selection final counts, so the gate checks
    # disk against exactly what was pinned (e.g. spoof-limited generators at their
    # true reachable ceiling, not an optimistic protocol count).
    _write_effective_targets(
        audit_csv=ROOT / args.audit_csv,
        report=summary["report"],
        out_path=out_dir / "effective_pool_audit.csv",
    )

    print(json.dumps({
        "total_selected": summary["total_selected"],
        "total_to_score": summary["total_to_score"],
        "n_shortfall_groups": len(summary["groups_with_shortfall"]),
        "selection_lock": str(selection_path),
        "score_manifest": str(manifest_path) if not manifest_df.empty else None,
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
