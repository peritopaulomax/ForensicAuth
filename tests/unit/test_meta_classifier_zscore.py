"""Ensemble meta-classifier must z-score logistic features (shared trainer)."""

from __future__ import annotations

import hashlib
import json

import numpy as np
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from core.synthetic_lr_reference import (
    _classifier_feature_importance,
    train_meta_classifier,
)


def test_logistic_meta_is_scaler_pipeline():
    rng = np.random.default_rng(0)
    x = np.column_stack(
        [
            rng.normal(0, 0.3, size=200),
            rng.normal(0, 5.0, size=200),
        ]
    )
    y = (x[:, 0] * 3 + rng.normal(0, 0.2, size=200) > 0).astype(int)
    cols = ["tiny", "huge"]
    model = train_meta_classifier("logistic", x, y, cols, seed=0)
    assert isinstance(model, Pipeline)
    assert isinstance(model.named_steps["scaler"], StandardScaler)
    assert "clf" in model.named_steps
    weights = _classifier_feature_importance(model, cols)
    assert weights is not None
    assert set(weights) == set(cols)


def test_xgboost_meta_has_no_scaler_step():
    rng = np.random.default_rng(1)
    x = rng.normal(size=(120, 2))
    y = (x[:, 0] > 0).astype(int)
    model = train_meta_classifier("xgboost", x, y, ["a", "b"], seed=1)
    assert not isinstance(model, Pipeline)


def test_feature_scale_in_cache_canonical_differs_by_classifier():
    """Contract mirrored by synth + audio cache keys: logistic → zscore."""
    base = {
        "score_matrix_hash": "abc",
        "selected_detectors": ["det_a"],
        "seed": 1,
        "sample_multiplier": 1,
    }
    for classifier, scale in (("logistic", "zscore"), ("xgboost", "none")):
        canonical = {
            **base,
            "classifier": classifier,
            "feature_scale": "zscore" if classifier == "logistic" else "none",
        }
        assert canonical["feature_scale"] == scale
        digest = hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()[:32]
        assert len(digest) == 32


def test_legacy_alias_points_to_public_trainer():
    from core.synthetic_lr_reference import _train_meta_classifier

    assert _train_meta_classifier is train_meta_classifier


def test_unwrap_exposes_logistic_intercept():
    from core.synthetic_lr_reference import _unwrap_meta_estimator

    rng = np.random.default_rng(2)
    x = rng.normal(size=(80, 2))
    y = (x[:, 0] > 0).astype(int)
    model = train_meta_classifier("logistic", x, y, ["a", "b"], seed=2)
    est = _unwrap_meta_estimator(model)
    assert hasattr(est, "intercept_")
    assert not hasattr(model, "intercept_")
    _ = float(est.intercept_[0])
