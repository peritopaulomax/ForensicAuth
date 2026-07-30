"""LR cache keys must survive absolute reference_data root changes."""

from __future__ import annotations

from pathlib import Path

from core.reference_data import paths as rd_paths
from core.synthetic_lr_reference import (
    PopulationItem,
    _cache_key_candidates,
    _normalize_matrix_text_for_hash,
    _score_matrix_hash,
)


def _reps_segment() -> str:
    for name in dir(rd_paths):
        if name.startswith("synthetic_") and name.endswith("_root") and "domain" not in name:
            return getattr(rd_paths, name)().name
    raise RuntimeError("synthetic representations root helper not found")


def test_normalize_matrix_text_collapses_reference_data_prefixes():
    seg = _reps_segment()
    left = (
        f"/home/a/proj/reference_data/synthetic_image/features/{seg}/a.npy,"
        f"/home/a/proj/reference_data/synthetic_image/features/{seg}/b.npy\n"
    )
    right = (
        f"/data/reference_data/synthetic_image/features/{seg}/a.npy,"
        f"/data/reference_data/synthetic_image/features/{seg}/b.npy\n"
    )
    assert _normalize_matrix_text_for_hash(left) == _normalize_matrix_text_for_hash(right)
    assert "<SYN_REPS>/a.npy" in _normalize_matrix_text_for_hash(right)


def test_score_matrix_hash_path_invariant(tmp_path: Path):
    seg = _reps_segment()
    a = tmp_path / "a.csv"
    b = tmp_path / "b.csv"
    a.write_text(
        f"p\n/tmp/host-a/reference_data/synthetic_image/features/{seg}/x.npy\n",
        encoding="utf-8",
    )
    b.write_text(
        f"p\n/var/lib/reference_data/synthetic_image/features/{seg}/x.npy\n",
        encoding="utf-8",
    )
    assert _score_matrix_hash(a) == _score_matrix_hash(b)


def test_cache_key_candidates_include_legacy_hashes(tmp_path: Path):
    seg = _reps_segment()
    matrix = tmp_path / "matrix.csv"
    matrix.write_text(
        f"p\n/tmp/reference_data/synthetic_image/features/{seg}/x.npy\n",
        encoding="utf-8",
    )
    items = [PopulationItem(base_group="GenImage", subgroup="Midjourney")]
    keys = _cache_key_candidates(
        score_matrix=matrix,
        macro_category=None,
        items=items,
        selected_detectors=("bfree",),
        classifier="logistic",
        seed=20260630,
        sample_multiplier=5,
        use_latent_typicality=True,
    )
    assert len(keys) >= 2
