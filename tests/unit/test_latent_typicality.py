"""Unit tests for latent typicality k-NN helpers (production module)."""

from __future__ import annotations

import numpy as np
import pytest

from core.latent_typicality.typicality import (
    build_typicality_reference,
    typicality_features_batch,
    typicality_features_for_embedding,
)


def test_typicality_reference_builds_and_scores():
    rng = np.random.default_rng(42)
    real = rng.normal(size=(40, 8))
    spoof = real + 2.5
    ref = build_typicality_reference(
        detector="demo",
        distance="euclidean",
        k=5,
        real_embeddings=real,
        synthetic_embeddings=spoof,
        real_ids=[f"r{i}" for i in range(40)],
        synthetic_ids=[f"s{i}" for i in range(40)],
    )
    query = real[0]
    feats = typicality_features_for_embedding(query, ref, exclude_self=True)
    assert 0.0 <= feats["T_R_demo"] <= 1.0
    assert 0.0 <= feats["T_S_demo"] <= 1.0
    assert feats["OOD_demo"] >= 0.0


def test_cosine_distance_reference():
    rng = np.random.default_rng(7)
    real = rng.normal(size=(30, 6))
    spoof = rng.normal(size=(30, 6)) + 1.0
    ref = build_typicality_reference(
        detector="demo",
        distance="cosine",
        k=5,
        real_embeddings=real,
        synthetic_embeddings=spoof,
        real_ids=[f"r{i}" for i in range(30)],
        synthetic_ids=[f"s{i}" for i in range(30)],
    )
    feats = typicality_features_for_embedding(real[3], ref, exclude_self=True)
    assert np.isfinite(feats["rho_demo"])


def test_typicality_batch_matches_rowwise():
    rng = np.random.default_rng(99)
    real = rng.normal(size=(40, 8))
    spoof = real + 1.5
    ref = build_typicality_reference(
        detector="demo",
        distance="euclidean",
        k=5,
        real_embeddings=real,
        synthetic_embeddings=spoof,
        real_ids=[f"r{i}" for i in range(40)],
        synthetic_ids=[f"s{i}" for i in range(40)],
    )
    queries = np.vstack([real[:10], spoof[:10], rng.normal(size=(5, 8))])
    exclude_self = np.array([True] * 10 + [False] * 15, dtype=bool)
    batch = typicality_features_batch(queries, ref, exclude_self=exclude_self)
    for idx, query in enumerate(queries):
        row = typicality_features_for_embedding(
            query,
            ref,
            exclude_self=bool(exclude_self[idx]),
        )
        for key, expected in row.items():
            assert key in batch
            assert batch[key][idx] == pytest.approx(expected, rel=1e-9, abs=1e-9)
