"""Tests for synthetic-image LR calibration with selectable meta-classifiers."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from core.synthetic_lr_reference import (
    META_CLASSIFIERS,
    REFERENCE_CATALOG,
    _default_items,
    compute_reference_lr,
)


def _make_synthetic_score_matrix(path, n_per_group: int = 160, seed: int = 42) -> None:
    rng = np.random.default_rng(seed)
    detectors = ["ai_image_detector_deploy", "sdxl_flux_detector_v1_1", "bfree", "corvi2023", "safe"]
    rows = []

    def _add(base_group: str, generator: str, y_fake: int, count: int) -> None:
        # Real images get high fake_prob on some detectors to simulate errors.
        base = 0.8 if y_fake == 1 else 0.3
        for _ in range(count):
            row = {
                "dataset": base_group,
                "generator": generator,
                "y_fake": y_fake,
                "error": "",
            }
            for detector in detectors:
                # Draw fake_prob around base with noise; keep in (0,1).
                p = float(np.clip(base + rng.normal(0.0, 0.15), 0.05, 0.95))
                row[f"{detector}_fake_prob"] = p
            rows.append(row)

    def _dataset(base_group: str) -> str:
        if base_group == "Defactify":
            return "Defactify_MS_COCOAI"
        if base_group == "OpenSDI":
            return "OpenSDI_test"
        if base_group.startswith("AIGIBench"):
            return "AIGIBench"
        return base_group

    for base_group, generators in REFERENCE_CATALOG.items():
        dataset = _dataset(base_group)
        for generator in generators:
            _add(dataset, generator, 1, n_per_group)
            real_generator = f"{generator}_real" if base_group.startswith("AIGIBench") else generator
            _add(dataset, real_generator, 0, n_per_group)

    df = pd.DataFrame(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


@pytest.fixture
def score_matrix(tmp_path):
    path = tmp_path / "lr_scores_synthetic.csv"
    _make_synthetic_score_matrix(path, n_per_group=200)
    return path


@pytest.fixture
def detector_scores():
    return {
        "ai_image_detector_deploy": {"fake_prob": 0.85},
        "sdxl_flux_detector_v1_1": {"fake_prob": 0.80},
        "bfree": {"fake_prob": 0.75},
        "corvi2023": {"fake_prob": 0.70},
        "safe": {"fake_prob": 0.72},
    }


@pytest.mark.parametrize("classifier", META_CLASSIFIERS)
def test_compute_reference_lr_with_each_classifier(score_matrix, detector_scores, classifier, tmp_path):
    out_dir = tmp_path / "lr_out"
    out_dir.mkdir()

    report = compute_reference_lr(
        detector_scores=detector_scores,
        selection={"items": ["GenImage/stable_diffusion_v_1_4", "AIGCDetectBenchmark/SDXL"]},
        out_dir=out_dir,
        seed=20260630,
        score_matrix=score_matrix,
        classifier=classifier,
    )

    assert report["meta_classifier"] == classifier
    assert report["meta_classifier_label"]
    assert "questioned" in report
    assert report["questioned"]["log10_lr"] is not None
    assert report["artifact_filenames"]["tippett"]
    assert report["artifact_filenames"]["distribution"]
    assert report["artifact_filenames"]["identity"]
    assert report["artifact_filenames"]["summary"]
    assert (out_dir / "lr_reference_report.json").is_file()
    assert (out_dir / report["artifact_filenames"]["summary"]).is_file()


def test_compute_reference_lr_invalid_classifier(score_matrix, detector_scores, tmp_path):
    out_dir = tmp_path / "lr_out"
    out_dir.mkdir()

    with pytest.raises(RuntimeError, match="Classificador meta"):
        compute_reference_lr(
            detector_scores=detector_scores,
            selection=None,
            out_dir=out_dir,
            seed=20260630,
            score_matrix=score_matrix,
            classifier="neural_network",
        )


def test_compute_reference_lr_subset_of_detectors(score_matrix, tmp_path):
    out_dir = tmp_path / "lr_out"
    out_dir.mkdir()

    detector_scores = {
        "ai_image_detector_deploy": {"fake_prob": 0.9},
        "bfree": {"fake_prob": 0.6},
    }

    report = compute_reference_lr(
        detector_scores=detector_scores,
        selection={"items": ["GenImage/stable_diffusion_v_1_4", "AIGCDetectBenchmark/SDXL"]},
        out_dir=out_dir,
        seed=20260630,
        score_matrix=score_matrix,
        selected_detectors=("ai_image_detector_deploy", "bfree"),
        classifier="logistic",
    )

    assert report["selected_detectors"] == ["ai_image_detector_deploy", "bfree"]
    assert report["questioned"]["log10_lr"] is not None


def test_compute_reference_lr_macro_cache(score_matrix, detector_scores, tmp_path):
    out_dir = tmp_path / "lr_out"
    out_dir.mkdir()

    first = compute_reference_lr(
        detector_scores=detector_scores,
        selection={"macro": "gan_older"},
        out_dir=out_dir,
        seed=20260630,
        score_matrix=score_matrix,
        classifier="logistic",
    )

    second = compute_reference_lr(
        detector_scores=detector_scores,
        selection={"macro": "gan_older"},
        out_dir=out_dir,
        seed=20260630,
        score_matrix=score_matrix,
        classifier="logistic",
    )

    assert second["used_cache"] is True
    assert second["selected_count"] == first["selected_count"]
    assert second["questioned"]["log10_lr"] is not None
