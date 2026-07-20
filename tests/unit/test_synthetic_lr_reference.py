"""Tests for synthetic-image LR calibration with selectable meta-classifiers."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from core.synthetic_lr_reference import (
    AUGMENTATION_MULTIPLIER,
    META_CLASSIFIERS,
    REFERENCE_CATALOG,
    _default_items,
    _filter_matrix_scope,
    compute_reference_lr,
)
from core.latent_typicality.representations_utils import ORIGINAL_AUGMENTATION_TAG


def _make_representations_matrix(
    score_matrix_path,
    representations_path,
    embed_dir,
    n_per_group: int = 60,
    embedding_dim: int = 16,
    seed: int = 42,
) -> None:
    """Build a tiny representations matrix with synthetic embeddings on disk."""
    rng = np.random.default_rng(seed)
    detectors = ["ai_image_detector_deploy", "sdxl_flux_detector_v1_1", "bfree", "corvi2023", "safe"]

    rows = []
    for base_group, generators in REFERENCE_CATALOG.items():
        dataset = base_group
        if base_group == "Defactify":
            dataset = "Defactify_MS_COCOAI"
        elif base_group == "OpenSDI":
            dataset = "OpenSDI_test"
        elif base_group.startswith("AIGIBench"):
            dataset = "AIGIBench"

        for generator in generators:
            for y_fake in (0, 1):
                gen = generator if y_fake == 1 else (f"{generator}_real" if base_group.startswith("AIGIBench") else generator)
                for _ in range(n_per_group):
                    sample_id = f"{dataset}__{gen}__{rng.integers(0, 1_000_000)}__original"
                    row = {
                        "sample_id": sample_id,
                        "dataset": dataset,
                        "generator": gen,
                        "y_fake": y_fake,
                        "error": "",
                        "augmentation": "",
                        "purpose": "reference_population",
                        "label": "fake" if y_fake else "real",
                        "source_id": sample_id,
                        "image_path": "tests/fixtures/images/copymove.jpg",
                    }
                    base_prob = 0.8 if y_fake == 1 else 0.3
                    for detector in detectors:
                        p = float(np.clip(base_prob + rng.normal(0.0, 0.15), 0.05, 0.95))
                        row[f"{detector}_fake_prob"] = p
                        row[f"{detector}_real_prob"] = 1.0 - p
                        row[f"{detector}_raw_score"] = 0.0
                        row[f"{detector}_decision"] = "AI" if p > 0.5 else "REAL"
                        emb = rng.normal(0.0, 1.0, size=embedding_dim).astype(np.float32)
                        if y_fake == 1:
                            emb[0] += 1.0
                        else:
                            emb[0] -= 1.0
                        emb_path = embed_dir / f"{sample_id}__{detector}.npy"
                        np.save(emb_path, emb)
                        row[f"{detector}_embedding_path"] = str(emb_path)
                        row[f"{detector}_embedding_dim"] = embedding_dim
                    rows.append(row)

    df = pd.DataFrame(rows)
    score_df = df.drop(
        columns=[c for c in df.columns if "_embedding" in c],
        errors="ignore",
    )
    score_matrix_path.parent.mkdir(parents=True, exist_ok=True)
    score_df.to_csv(score_matrix_path, index=False)

    representations_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(representations_path, index=False)


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


@pytest.fixture
def representations_matrix(tmp_path):
    score_path = tmp_path / "lr_scores_synthetic.csv"
    rep_path = tmp_path / "representations.csv"
    embed_dir = tmp_path / "embeddings"
    embed_dir.mkdir()
    _make_representations_matrix(score_path, rep_path, embed_dir, n_per_group=60, embedding_dim=16)
    return rep_path


def _detector_scores_with_embeddings():
    rng = np.random.default_rng(123)
    dim = 16
    return {
        "ai_image_detector_deploy": {"fake_prob": 0.85, "embedding": rng.normal(0.0, 1.0, size=dim).astype(np.float32)},
        "sdxl_flux_detector_v1_1": {"fake_prob": 0.80, "embedding": rng.normal(0.0, 1.0, size=dim).astype(np.float32)},
        "bfree": {"fake_prob": 0.75, "embedding": rng.normal(0.0, 1.0, size=dim).astype(np.float32)},
        "corvi2023": {"fake_prob": 0.70, "embedding": rng.normal(0.0, 1.0, size=dim).astype(np.float32)},
        "safe": {"fake_prob": 0.72, "embedding": rng.normal(0.0, 1.0, size=dim).astype(np.float32)},
    }


def test_filter_matrix_scope_original_only():
    df = pd.DataFrame(
        {
            "augmentation": ["", ORIGINAL_AUGMENTATION_TAG, "jpeg_85"],
            "value": [1, 2, 3],
        }
    )
    filtered = _filter_matrix_scope(df, augmented_reference=False)
    assert len(filtered) == 2
    assert "jpeg_85" not in filtered["augmentation"].tolist()


def test_compute_reference_lr_latent_typicality_augmented_flags(representations_matrix, tmp_path):
    out_dir = tmp_path / "lr_out"
    out_dir.mkdir()
    report = compute_reference_lr(
        detector_scores=_detector_scores_with_embeddings(),
        selection={"items": ["GenImage/stable_diffusion_v_1_4"]},
        out_dir=out_dir,
        seed=20260630,
        score_matrix=representations_matrix,
        sample_multiplier=AUGMENTATION_MULTIPLIER,
        use_latent_typicality=True,
        classifier="logistic",
    )
    assert report["augmented_reference"] is True
    assert report["sample_multiplier"] == AUGMENTATION_MULTIPLIER
    assert report["use_latent_typicality"] is True


def test_compute_reference_lr_latent_typicality(representations_matrix, tmp_path):
    out_dir = tmp_path / "lr_out"
    out_dir.mkdir()

    detector_scores = _detector_scores_with_embeddings()
    report = compute_reference_lr(
        detector_scores=detector_scores,
        selection={"items": ["GenImage/stable_diffusion_v_1_4", "AIGCDetectBenchmark/SDXL"]},
        out_dir=out_dir,
        seed=20260630,
        score_matrix=representations_matrix,
        use_latent_typicality=True,
        typicality_system="D",
        typicality_k=5,
        typicality_distance="cosine",
        classifier="logistic",
    )

    assert report["meta_classifier"] == "logistic"
    assert report["questioned"]["log10_lr"] is not None
    assert report["artifact_filenames"]["tippett"]
    assert (out_dir / "lr_reference_report.json").is_file()


def test_compute_reference_lr_latent_typicality_subset(representations_matrix, tmp_path):
    out_dir = tmp_path / "lr_out"
    out_dir.mkdir()

    detector_scores = {
        "ai_image_detector_deploy": {"fake_prob": 0.85, "embedding": np.random.default_rng(1).normal(0.0, 1.0, size=16).astype(np.float32)},
        "bfree": {"fake_prob": 0.65, "embedding": np.random.default_rng(2).normal(0.0, 1.0, size=16).astype(np.float32)},
    }
    report = compute_reference_lr(
        detector_scores=detector_scores,
        selection={"items": ["GenImage/stable_diffusion_v_1_4"]},
        out_dir=out_dir,
        seed=20260630,
        score_matrix=representations_matrix,
        selected_detectors=("ai_image_detector_deploy", "bfree"),
        use_latent_typicality=True,
        typicality_system="B",
        typicality_k=5,
        classifier="logistic",
    )

    assert report["selected_detectors"] == ["ai_image_detector_deploy", "bfree"]
    assert report["questioned"]["log10_lr"] is not None


def test_compute_reference_lr_latent_typicality_cache(representations_matrix, tmp_path):
    out_dir = tmp_path / "lr_out"
    out_dir.mkdir()

    detector_scores = _detector_scores_with_embeddings()
    first = compute_reference_lr(
        detector_scores=detector_scores,
        selection={"items": ["GenImage/stable_diffusion_v_1_4"]},
        out_dir=out_dir,
        seed=20260630,
        score_matrix=representations_matrix,
        use_latent_typicality=True,
        classifier="logistic",
    )

    second = compute_reference_lr(
        detector_scores=detector_scores,
        selection={"items": ["GenImage/stable_diffusion_v_1_4"]},
        out_dir=out_dir,
        seed=20260630,
        score_matrix=representations_matrix,
        use_latent_typicality=True,
        classifier="logistic",
    )

    assert second["used_cache"] is True
    assert second["questioned"]["log10_lr"] is not None
