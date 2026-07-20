#!/usr/bin/env python3
"""Physical completion gate for LR reference population (500+500)×5 per eligible generator."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src" / "backend"))

from audio_lr_disk_verify import (  # noqa: E402
    DETECTORS,
    TARGET_PER_CLASS,
    UNITS_PER_ELIGIBLE_GENERATOR,
    audit_to_row,
    run_disk_audit,
)
from core.latent_typicality.representations_utils import source_id_stem  # noqa: E402


def check_matrix_integrity(score_matrix: Path) -> dict:
    """Verify the score matrix has zero NaN logits and zero duplicate source ids.

    A green gate REQUIRES this: LR calibration cannot tolerate NaN features nor
    duplicated reference samples.
    """
    import numpy as np
    import pandas as pd

    result = {"ok": False, "nan_logit_rows": None, "duplicate_rows": None, "error_rows": None}
    if not score_matrix.is_file():
        result["message"] = f"score matrix ausente: {score_matrix}"
        return result

    df = pd.read_csv(score_matrix, low_memory=False)
    if "error" in df.columns:
        blank = df["error"].isna() | df["error"].astype(str).str.strip().isin(["", "nan"])
        error_rows = int((~blank).sum())
        ok = df[blank].copy()
    else:
        error_rows = 0
        ok = df.copy()

    logit_cols = [f"{det}_bonafide_logit" for det in DETECTORS]
    present = [c for c in logit_cols if c in ok.columns]
    if present:
        vals = ok[present].apply(pd.to_numeric, errors="coerce")
        nan_rows = int((~np.isfinite(vals.to_numpy(dtype=float))).any(axis=1).sum())
    else:
        nan_rows = len(ok)

    sid = ok["source_id"].astype(str).map(source_id_stem)
    dup_mask = ok.assign(_sid=sid).duplicated(
        subset=["dataset", "generator", "label", "_sid"], keep=False
    )
    dup_rows = int(dup_mask.sum())

    result.update(
        {
            "ok": nan_rows == 0 and dup_rows == 0 and error_rows == 0,
            "nan_logit_rows": nan_rows,
            "duplicate_rows": dup_rows,
            "error_rows": error_rows,
        }
    )
    return result


def check_representations_integrity(representations_csv: Path, score_matrix: Path) -> dict:
    """Verify the latent-typicality representations matrix is calibration-clean.

    The typicality features read the detector score straight from each representation
    row, so this matrix must also have zero NaN logits. It must additionally carry no
    "orphan" generator groups (present here but absent from the sanitized score matrix),
    which are stale/superseded pools that would pollute the reference population.
    """
    import numpy as np
    import pandas as pd

    result = {"ok": False, "nan_logit_rows": None, "orphan_groups": None}
    if not representations_csv.is_file():
        result["message"] = f"representations ausente: {representations_csv}"
        return result

    df = pd.read_csv(representations_csv, low_memory=False)
    logit_cols = [f"{det}_bonafide_logit" for det in DETECTORS]
    present = [c for c in logit_cols if c in df.columns]
    if present:
        vals = df[present].apply(pd.to_numeric, errors="coerce")
        nan_rows = int((~np.isfinite(vals.to_numpy(dtype=float))).any(axis=1).sum())
    else:
        nan_rows = len(df)

    orphan_groups: list[list[str]] = []
    if score_matrix.is_file():
        matrix = pd.read_csv(score_matrix, low_memory=False)
        matrix_groups = set(zip(matrix["dataset"].astype(str), matrix["generator"].astype(str)))
        rep_groups = set(zip(df["dataset"].astype(str), df["generator"].astype(str)))
        orphan_groups = sorted([list(g) for g in (rep_groups - matrix_groups)])

    result.update(
        {
            "ok": nan_rows == 0 and len(orphan_groups) == 0,
            "nan_logit_rows": nan_rows,
            "orphan_groups": orphan_groups,
        }
    )
    return result


def _write_markdown_report(report: dict, path: Path) -> None:
    lines = [
        "# Audio LR Completion Gate Report",
        "",
        f"- **Passed:** {report.get('passed')}",
        f"- **Eligible passed:** {report.get('eligible_passed')}",
        f"- **Global progress:** {report.get('global_pct')}% ({report.get('global_units_ok')}/{report.get('global_units_target')})",
        f"- **Eligible progress:** {report.get('eligible_pct')}% ({report.get('eligible_units_ok')}/{report.get('eligible_units_target')})",
        f"- **Matrix integrity:** {report.get('matrix_integrity')}",
        f"- **Representations integrity:** {report.get('representations_integrity')}",
        "",
        "## Ineligible generators (pool < 500 unique per class)",
        "",
    ]
    for item in report.get("ineligible_generators") or []:
        lines.append(f"- {item}")
    lines.extend(["", "## Gaps by generator", ""])
    for gen in report.get("by_generator") or []:
        if gen.get("passed"):
            continue
        lines.append(f"### {gen['dataset']}/{gen['generator']} ({gen.get('pct')}%)")
        for gap in gen.get("gaps") or []:
            lines.append(f"- {gap['field']}: {gap['have']}/{gap['need']}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-dir", default="outputs/lr_calibration/audio_spoofing")
    parser.add_argument("--out-dir", default="outputs/lr_calibration/audio_spoofing/inventory")
    parser.add_argument("--protocol-audit", default=None)
    parser.add_argument("--loop-iteration", type=int, default=0)
    parser.add_argument("--eta-hours", type=float, default=None)
    args = parser.parse_args()

    base_dir = ROOT / args.base_dir
    out_dir = ROOT / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    # Prefer the reconciled effective targets (frozen selection finals); fall back
    # to the raw protocol pool audit.
    if args.protocol_audit:
        protocol_audit = ROOT / args.protocol_audit
    else:
        effective = out_dir / "effective_pool_audit.csv"
        protocol_audit = effective if effective.is_file() else out_dir / "protocol_pool_audit.csv"

    score_matrix = base_dir / "score_matrices/lr_scores_balanced_full.csv"
    representations_csv = base_dir / "representations/representations.csv"
    matrix_integrity = check_matrix_integrity(score_matrix)
    representations_integrity = check_representations_integrity(representations_csv, score_matrix)

    audits, summary = run_disk_audit(base_dir=base_dir, protocol_audit_csv=protocol_audit)
    # A green gate requires a clean score matrix AND a clean representations matrix
    # (no NaN, no duplicates/errors, no orphan generator groups): the typicality path
    # reads scores straight from representations.csv.
    summary["matrix_integrity"] = matrix_integrity
    summary["representations_integrity"] = representations_integrity
    if not matrix_integrity["ok"] or not representations_integrity["ok"]:
        summary["passed"] = False
        summary["eligible_passed"] = False

    by_generator = []
    for audit in audits:
        entry = {
            "dataset": audit.dataset,
            "generator": audit.generator,
            "eligible_500": audit.eligible_500,
            "pct": audit.pct,
            "units_ok": audit.units_ok,
            "target_units": audit.target_units,
            "passed": audit.passed,
            "bf_orig": f"{audit.orig_bonafide.complete_units}/{audit.target_bf_orig}",
            "sp_orig": f"{audit.orig_spoof.complete_units}/{audit.target_sp_orig}",
            "bf_aug": f"{audit.aug_bonafide.complete_units}/{audit.target_bf_aug}",
            "sp_aug": f"{audit.aug_spoof.complete_units}/{audit.target_sp_aug}",
            "gaps": audit.gaps,
            "status": "ok" if audit.passed else "gap",
        }
        by_generator.append(entry)

    report = {
        **summary,
        "target_per_eligible_generator": UNITS_PER_ELIGIBLE_GENERATOR,
        "target_per_class": TARGET_PER_CLASS,
        "by_generator": by_generator,
    }
    report_path = out_dir / "completion_gate_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    progress = {
        "target_per_eligible_generator": UNITS_PER_ELIGIBLE_GENERATOR,
        "eligible_generators": summary["eligible_generators"],
        "ineligible_generators": summary["ineligible_generators"],
        "global_units_ok": summary["global_units_ok"],
        "global_units_target": summary["global_units_target"],
        "global_pct": summary["global_pct"],
        "eligible_units_ok": summary["eligible_units_ok"],
        "eligible_units_target": summary["eligible_units_target"],
        "eligible_pct": summary["eligible_pct"],
        "loop_iteration": args.loop_iteration,
        "eta_hours_remaining": args.eta_hours,
        "passed": summary["passed"],
        "eligible_passed": summary["eligible_passed"],
        "by_generator": by_generator,
    }
    progress_path = out_dir / "completion_progress.json"
    progress_path.write_text(json.dumps(progress, indent=2, ensure_ascii=False), encoding="utf-8")

    detail_csv = out_dir / "disk_audit_by_generator.csv"
    import pandas as pd

    pd.DataFrame([audit_to_row(a) for a in audits]).to_csv(detail_csv, index=False)

    md_path = out_dir / "completion_gate_report.md"
    _write_markdown_report(report, md_path)

    print(json.dumps({
        "passed": summary["passed"],
        "eligible_passed": summary["eligible_passed"],
        "eligible_pct": summary["eligible_pct"],
        "matrix_integrity": matrix_integrity,
        "representations_integrity": representations_integrity,
    }, indent=2))
    print(f"Wrote {report_path}")
    print(f"Wrote {progress_path}")

    if not matrix_integrity["ok"]:
        print(
            f"\nGATE FAIL — matriz suja: {matrix_integrity['nan_logit_rows']} NaN, "
            f"{matrix_integrity['duplicate_rows']} duplicatas, {matrix_integrity['error_rows']} linhas de erro",
            flush=True,
        )
        return 1

    if not representations_integrity["ok"]:
        print(
            f"\nGATE FAIL — representations suja: {representations_integrity['nan_logit_rows']} NaN, "
            f"{len(representations_integrity['orphan_groups'] or [])} grupos orfaos "
            f"{representations_integrity['orphan_groups']}",
            flush=True,
        )
        return 1

    if not summary["passed"]:
        failing = [g for g in by_generator if not g["passed"]]
        print(f"\nGATE FAIL — {len(failing)} geradores com lacunas (alvo real)", flush=True)
        for g in failing[:15]:
            print(f"  {g['dataset']}/{g['generator']}: {g['bf_orig']} bf_orig, {g['sp_orig']} sp_orig, {g['bf_aug']} bf_aug, {g['sp_aug']} sp_aug", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
