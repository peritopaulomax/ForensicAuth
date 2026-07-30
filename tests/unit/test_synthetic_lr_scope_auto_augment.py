"""Auto-promote augmented reference when originals are missing from the matrix."""

from __future__ import annotations

import pandas as pd
import pytest

from core.synthetic_lr_reference import (
    AUGMENTATION_MULTIPLIER,
    PopulationItem,
    _resolve_scope_for_population,
)


def _aigc_aug_only_df() -> pd.DataFrame:
    rows = []
    for aug in ("jpeg_85", "webp_80", "crop_upscale", "resize_down_50"):
        rows.append(
            {
                "dataset": "AIGCDetectBenchmark",
                "generator": "ADM",
                "y_fake": 1,
                "augmentation": aug,
            }
        )
        rows.append(
            {
                "dataset": "AIGCDetectBenchmark",
                "generator": "Real",
                "y_fake": 0,
                "augmentation": aug,
            }
        )
    return pd.DataFrame(rows)


def test_resolve_scope_auto_promotes_when_only_augmented_rows_exist():
    df = _aigc_aug_only_df()
    items = [PopulationItem("AIGCDetectBenchmark", "ADM")]
    scoped, aug, mult, promoted = _resolve_scope_for_population(
        df,
        items,
        augmented_reference=False,
        sample_multiplier=1,
    )
    assert aug is True
    assert mult == AUGMENTATION_MULTIPLIER
    assert promoted == ["AIGCDetectBenchmark/ADM"]
    assert not scoped.empty
    assert set(scoped["augmentation"]) == {
        "jpeg_85",
        "webp_80",
        "crop_upscale",
        "resize_down_50",
    }


def test_resolve_scope_keeps_originals_when_present():
    df = pd.DataFrame(
        [
            {
                "dataset": "AIGCDetectBenchmark",
                "generator": "ADM",
                "y_fake": 1,
                "augmentation": "original",
            },
            {
                "dataset": "AIGCDetectBenchmark",
                "generator": "ADM",
                "y_fake": 1,
                "augmentation": "jpeg_85",
            },
        ]
    )
    items = [PopulationItem("AIGCDetectBenchmark", "ADM")]
    scoped, aug, mult, promoted = _resolve_scope_for_population(
        df,
        items,
        augmented_reference=False,
        sample_multiplier=1,
    )
    assert aug is False
    assert mult == 1
    assert promoted == []
    assert list(scoped["augmentation"]) == ["original"]


def test_resolve_scope_raises_when_population_absent():
    df = pd.DataFrame(
        [
            {
                "dataset": "GenImage",
                "generator": "ADM",
                "y_fake": 1,
                "augmentation": "jpeg_85",
            }
        ]
    )
    items = [PopulationItem("AIGCDetectBenchmark", "ADM")]
    with pytest.raises(RuntimeError, match="nenhum candidato fake"):
        _resolve_scope_for_population(
            df,
            items,
            augmented_reference=False,
            sample_multiplier=1,
        )
