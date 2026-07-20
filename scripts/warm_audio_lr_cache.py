#!/usr/bin/env python3
"""Pre-warm audio LR calibration cache for common reference presets."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "backend"))

from core.audio_spoofing_lr_reference import (  # noqa: E402
    DEFAULT_REPRESENTATIONS_MATRIX,
    DEFAULT_SCORE_MATRIX,
    DEFAULT_VOICE_CLONE_REFERENCE,
    PopulationItem,
    compute_reference_lr,
    representations_matrix_available,
)

PRESETS: dict[str, dict] = {
    "voice_clone_default": {
        "items": list(DEFAULT_VOICE_CLONE_REFERENCE),
        "use_latent_typicality": False,
        "sample_multiplier": 1,
    },
    "voice_clone_augmented": {
        "items": list(DEFAULT_VOICE_CLONE_REFERENCE),
        "use_latent_typicality": False,
        "sample_multiplier": 5,
    },
    "voice_clone_latent": {
        "items": list(DEFAULT_VOICE_CLONE_REFERENCE),
        "use_latent_typicality": True,
        "sample_multiplier": 1,
    },
    "in_the_wild": {
        "items": [PopulationItem("In-The-Wild", "In-The-Wild")],
        "use_latent_typicality": False,
        "sample_multiplier": 1,
    },
}


def _dummy_detector_scores() -> dict:
    detectors = ("df_arena_1b", "sls_xlsr", "wedefense_wavlm_mhfa")
    out = {}
    for det in detectors:
        out[det] = {
            "bonafide_logit": 0.0,
            "bonafide_prob": 0.5,
            "spoof_prob": 0.5,
            "embedding": [0.0] * 8,
        }
    return out


def warm_preset(name: str, *, out_root: Path) -> None:
    cfg = PRESETS[name]
    use_latent = bool(cfg["use_latent_typicality"])
    matrix = DEFAULT_REPRESENTATIONS_MATRIX if use_latent else DEFAULT_SCORE_MATRIX
    if not matrix.is_file():
        print(f"[skip] {name}: matriz ausente ({matrix})")
        return
    if use_latent and not representations_matrix_available(matrix):
        print(f"[skip] {name}: representations invalida ({matrix})")
        return
    out_dir = out_root / name
    out_dir.mkdir(parents=True, exist_ok=True)
    report = compute_reference_lr(
        detector_scores=_dummy_detector_scores(),
        selection={"items": [{"base_group": i.base_group, "subgroup": i.subgroup} for i in cfg["items"]]},
        out_dir=out_dir,
        selected_detectors=("df_arena_1b", "sls_xlsr", "wedefense_wavlm_mhfa"),
        sample_multiplier=int(cfg["sample_multiplier"]),
        use_latent_typicality=use_latent,
    )
    cache_hit = report.get("used_cache")
    print(f"[ok] {name}: cache_hit={cache_hit} rows={report.get('sample_rows')}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--preset",
        choices=sorted(PRESETS.keys()),
        action="append",
        help="Preset a aquecer (repita para varios)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Aquecer todos os presets disponiveis",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ROOT / "outputs" / "lr_calibration" / "cache_warm",
    )
    args = parser.parse_args()
    names = sorted(PRESETS.keys()) if args.all else (args.preset or ["voice_clone_default"])
    for name in names:
        warm_preset(name, out_root=args.out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
