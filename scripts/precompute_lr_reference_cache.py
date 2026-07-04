#!/usr/bin/env python3
"""Pre-compute reference-population meta-classifier caches.

Generates one cache for every non-empty combination of the five macro
technology categories and for the selected meta-classifiers. The cache key is
deterministic, so any later analysis that selects exactly the same set of
base/generator items (or the equivalent macro combination) reuses the cached
meta-classifier and LR calibration.

Example::

    python scripts/precompute_lr_reference_cache.py \
        --score-matrix outputs/lr_calibration/score_matrices/lr_scores_balanced_full.csv \
        --classifiers logistic xgboost
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from itertools import chain, combinations
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_BACKEND = PROJECT_ROOT / "src" / "backend"
if str(SRC_BACKEND) not in sys.path:
    sys.path.insert(0, str(SRC_BACKEND))

from core.synthetic_lr_reference import (
    ALL_DETECTORS,
    META_CLASSIFIERS,
    REFERENCE_MACRO_CATEGORIES,
    compute_reference_lr,
)


def _dummy_detector_scores() -> dict[str, dict[str, float]]:
    return {detector: {"fake_prob": 0.5} for detector in ALL_DETECTORS}


def _macro_combinations(macros: list[str]) -> list[tuple[str, ...]]:
    """Return all non-empty combinations of the given macros."""
    return list(
        chain.from_iterable(combinations(macros, r) for r in range(1, len(macros) + 1))
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pre-compute LR reference meta-classifier caches by macro-category combination."
    )
    parser.add_argument(
        "--score-matrix",
        type=Path,
        default=PROJECT_ROOT
        / "outputs"
        / "lr_calibration"
        / "score_matrices"
        / "lr_scores_balanced_full.csv",
        help="Path to the reference score matrix CSV.",
    )
    parser.add_argument(
        "--classifiers",
        nargs="+",
        choices=META_CLASSIFIERS,
        default=["logistic", "xgboost"],
        help="Meta-classifiers to pre-compute.",
    )
    parser.add_argument(
        "--macros",
        nargs="+",
        choices=list(REFERENCE_MACRO_CATEGORIES.keys()),
        default=list(REFERENCE_MACRO_CATEGORIES.keys()),
        help="Macro categories to combine.",
    )
    parser.add_argument(
        "--detectors",
        nargs="+",
        choices=list(ALL_DETECTORS),
        default=list(ALL_DETECTORS),
        help="Detectors to include in the cached models.",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=PROJECT_ROOT / "outputs" / "lr_calibration" / "cache" / "precompute_report.json",
        help="Path to write the JSON report.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=20260630,
        help="Random seed used for train/test split.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    if not args.score_matrix.is_file():
        print(f"Score matrix not found: {args.score_matrix}", file=sys.stderr)
        return 1

    macro_combos = _macro_combinations(args.macros)
    print(
        f"Pre-computing {len(macro_combos)} macro combinations × {len(args.classifiers)} classifiers = "
        f"{len(macro_combos) * len(args.classifiers)} caches...",
        flush=True,
    )

    report: list[dict] = []
    total_start = time.time()

    for combo in macro_combos:
        combo_label = " + ".join(combo)
        selection: dict = {"macros": list(combo)} if len(combo) > 1 else {"macro": combo[0]}
        for classifier in args.classifiers:
            key = f"{combo_label}/{classifier}"
            print(f"Pre-computing {key} ...", flush=True)
            start = time.time()
            try:
                with tempfile.TemporaryDirectory() as tmp_dir:
                    result = compute_reference_lr(
                        detector_scores=_dummy_detector_scores(),
                        selection=selection,
                        out_dir=Path(tmp_dir),
                        seed=args.seed,
                        score_matrix=args.score_matrix,
                        selected_detectors=tuple(args.detectors),
                        classifier=classifier,
                    )
                elapsed = time.time() - start
                report.append(
                    {
                        "macros": list(combo),
                        "classifier": classifier,
                        "status": "ok",
                        "elapsed_seconds": elapsed,
                        "cache_used": result.get("used_cache", False),
                        "selected_count": result.get("selected_count"),
                        "test_metrics": result.get("test_metrics", {}),
                    }
                )
                print(
                    f"  OK in {elapsed:.1f}s (cache_used={result.get('used_cache', False)})",
                    flush=True,
                )
            except Exception as exc:  # noqa: BLE001
                elapsed = time.time() - start
                report.append(
                    {
                        "macros": list(combo),
                        "classifier": classifier,
                        "status": "error",
                        "elapsed_seconds": elapsed,
                        "error": str(exc),
                    }
                )
                print(f"  ERROR after {elapsed:.1f}s: {exc}", file=sys.stderr, flush=True)

    summary = {
        "score_matrix": str(args.score_matrix),
        "detectors": list(args.detectors),
        "classifiers": args.classifiers,
        "total_elapsed_seconds": time.time() - total_start,
        "entries": report,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"\nReport written to {args.report}")

    errors = [entry for entry in report if entry["status"] == "error"]
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
