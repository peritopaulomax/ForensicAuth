"""Synthetic-image LR: fit/test role selection and product default population."""

from __future__ import annotations

import pytest

from core.synthetic_lr_reference import (
    DEFAULT_MODERN_REFERENCE,
    PopulationItem,
    default_reference_population,
    normalize_reference_selection,
    normalize_reference_selection_roles,
)


def test_default_modern_includes_transformer_cnn_and_socialrf():
    keys = {item.key for item in DEFAULT_MODERN_REFERENCE}
    assert "AIGIBench_SocialRF/SocialRF" in keys
    assert "AIGIBench_no_SocialRF/FLUX1-dev" in keys  # transformer
    assert "GenImage/Midjourney" in keys  # cnn modern
    assert "AIGCDetectBenchmark/ProGAN" not in keys  # gan older excluded
    payload = default_reference_population()
    assert len(payload) == len(DEFAULT_MODERN_REFERENCE)
    assert all("base_group" in row and "subgroup" in row for row in payload)


def test_normalize_empty_items_falls_back_to_default_modern():
    items = normalize_reference_selection({"items": []})
    assert {i.key for i in items} == {i.key for i in DEFAULT_MODERN_REFERENCE}


def test_normalize_roles_split_fit_and_test():
    fit = [{"base_group": "GenImage", "subgroup": "Midjourney"}]
    test = [{"base_group": "AIGIBench_SocialRF", "subgroup": "SocialRF"}]
    roles = normalize_reference_selection_roles({"fit_items": fit, "test_items": test})
    assert roles.fit_keys == frozenset({"GenImage/Midjourney"})
    assert roles.test_keys == frozenset({"AIGIBench_SocialRF/SocialRF"})
    assert {i.key for i in roles.union_items} == {
        "GenImage/Midjourney",
        "AIGIBench_SocialRF/SocialRF",
    }


def test_normalize_roles_items_fallback_copies_to_fit_and_test():
    roles = normalize_reference_selection_roles(
        {"items": [{"base_group": "OpenSDI", "subgroup": "flux"}]}
    )
    assert roles.fit_items == roles.test_items
    assert roles.fit_items == (PopulationItem("OpenSDI", "flux"),)


def test_normalize_roles_rejects_empty_fit():
    with pytest.raises(ValueError, match="fit_items"):
        normalize_reference_selection_roles(
            {
                "fit_items": [],
                "test_items": [{"base_group": "OpenSDI", "subgroup": "flux"}],
            }
        )
