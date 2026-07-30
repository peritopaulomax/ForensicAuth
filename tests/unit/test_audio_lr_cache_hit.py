"""Audio LR cache: HIT must unpack the 6-tuple from shared ``_load_lr_cache``."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from core.audio_spoofing_lr_reference import (
    PopulationItem,
    ReferenceSelectionRoles,
    _cache_key_from_parts,
    _load_audio_lr_cache,
    compute_reference_lr,
)
from core.reference_data import paths as rd_paths


@pytest.fixture(autouse=True)
def _clear_paths():
    rd_paths.clear_path_cache()
    yield
    rd_paths.clear_path_cache()


def test_load_audio_lr_cache_accepts_six_tuple(monkeypatch, tmp_path):
    scored = pd.DataFrame({"reference_split": ["test_bigauss"], "y_fake": [0], "log10_lr": [0.1]})
    payload = (
        MagicMock(name="model"),
        {"eer": 0.1, "sigma": 1.0, "mu_fake": 0.0, "mu_real": 1.0},
        ["df_arena_1b_bonafide_logit"],
        ("df_arena_1b",),
        scored,
        {"bonafide": MagicMock(name="tip_ref")},
    )

    monkeypatch.setattr(
        "core.audio_spoofing_lr_reference._load_lr_cache",
        lambda key: payload,
    )
    loaded = _load_audio_lr_cache("abc")
    assert loaded is not None
    assert len(loaded) == 6
    assert loaded[4] is scored
    assert loaded[5] is not None


def test_cache_key_from_parts_stable():
    roles = ReferenceSelectionRoles(
        fit_items=(PopulationItem("DFADD", "StyleTTS2"),),
        test_items=(PopulationItem("DFADD", "StyleTTS2"),),
    )
    a = _cache_key_from_parts(
        score_matrix_hash="deadbeef",
        roles=roles,
        selected_detectors=("df_arena_1b",),
        classifier="logistic",
        seed=1,
        sample_multiplier=1,
        use_latent_typicality=False,
    )
    b = _cache_key_from_parts(
        score_matrix_hash="deadbeef",
        roles=roles,
        selected_detectors=("df_arena_1b",),
        classifier="logistic",
        seed=1,
        sample_multiplier=1,
        use_latent_typicality=False,
    )
    assert a == b
    assert len(a) == 32
