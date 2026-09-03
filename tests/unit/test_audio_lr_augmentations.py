"""Granular audio LR augmentations: filter, multiplier, cache key isolation."""

from __future__ import annotations

import pandas as pd
import pytest

from core.audio_spoofing_lr_reference import (
    AUGMENTATION_NAMES,
    ORIGINAL_AUGMENTATION_TAG,
    PopulationItem,
    ReferenceSelectionRoles,
    _cache_key_from_parts,
    _filter_matrix_scope,
    normalize_reference_augmentations,
    sample_multiplier_for_augmentations,
)


def _roles() -> ReferenceSelectionRoles:
    return ReferenceSelectionRoles(
        fit_items=(PopulationItem("MLAAD_PT", "Voxtral"),),
        test_items=(PopulationItem("MLAAD_PT", "Voxtral"),),
    )


def test_normalize_list_wins_over_legacy_flag():
    assert normalize_reference_augmentations(
        ["opus_32k", "mp3_128k"],
        use_augmented_reference=True,
    ) == ("mp3_128k", "opus_32k")
    assert normalize_reference_augmentations([], use_augmented_reference=True) == ()
    assert normalize_reference_augmentations(None, use_augmented_reference=True) == AUGMENTATION_NAMES
    assert normalize_reference_augmentations(None, use_augmented_reference=False) == ()


def test_normalize_rejects_unknown_and_non_list():
    with pytest.raises(ValueError, match="invalidas"):
        normalize_reference_augmentations(["mp3_128k", "aac_96k"])
    with pytest.raises(TypeError, match="lista"):
        normalize_reference_augmentations("mp3_128k")


def test_sample_multiplier_counts_original_plus_selected():
    assert sample_multiplier_for_augmentations(()) == 1
    assert sample_multiplier_for_augmentations(("mp3_128k",)) == 2
    assert sample_multiplier_for_augmentations(AUGMENTATION_NAMES) == 1 + len(AUGMENTATION_NAMES)


def test_filter_matrix_keeps_originals_and_selected_tags():
    df = pd.DataFrame(
        {
            "augmentation": [
                "",
                ORIGINAL_AUGMENTATION_TAG,
                "mp3_128k",
                "opus_32k",
                "noise_snr_20",
                "noise_snr_15",
            ],
            "y_fake": [0, 1, 0, 1, 0, 1],
        }
    )
    scoped = _filter_matrix_scope(df, selected_augmentations=("mp3_128k", "noise_snr_15"))
    assert set(scoped["augmentation"]) == {
        "",
        ORIGINAL_AUGMENTATION_TAG,
        "mp3_128k",
        "noise_snr_15",
    }

    originals = _filter_matrix_scope(df, selected_augmentations=())
    assert set(originals["augmentation"]) == {"", ORIGINAL_AUGMENTATION_TAG}


def test_cache_key_full_catalog_matches_legacy_multiplier_only():
    roles = _roles()
    kwargs = dict(
        score_matrix_hash="deadbeef",
        roles=roles,
        selected_detectors=("df_arena_1b",),
        classifier="logistic",
        seed=1,
        use_latent_typicality=False,
    )
    legacy = _cache_key_from_parts(**kwargs, sample_multiplier=5)
    full = _cache_key_from_parts(
        **kwargs,
        sample_multiplier=5,
        selected_augmentations=AUGMENTATION_NAMES,
    )
    originals = _cache_key_from_parts(**kwargs, sample_multiplier=1)
    empty_explicit = _cache_key_from_parts(
        **kwargs, sample_multiplier=1, selected_augmentations=()
    )
    assert legacy == full
    assert originals == empty_explicit
    assert legacy != originals


def test_cache_key_same_multiplier_different_subsets_diverge():
    roles = _roles()
    kwargs = dict(
        score_matrix_hash="deadbeef",
        roles=roles,
        selected_detectors=("df_arena_1b",),
        classifier="logistic",
        seed=1,
        sample_multiplier=3,
        use_latent_typicality=False,
    )
    codecs = _cache_key_from_parts(
        **kwargs, selected_augmentations=("mp3_128k", "opus_32k")
    )
    noise = _cache_key_from_parts(
        **kwargs, selected_augmentations=("noise_snr_20", "noise_snr_15")
    )
    assert codecs != noise
