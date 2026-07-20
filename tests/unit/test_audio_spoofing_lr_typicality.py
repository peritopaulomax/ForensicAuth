"""Tests for audio LR with latent typicality."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from core.audio_spoofing_lr_reference import (
    DEFAULT_VOICE_CLONE_REFERENCE,
    PopulationItem,
    ReferenceSelectionRoles,
    _build_typicality_refs,
    _cache_key,
    _filter_matrix_scope,
    _filter_rows_with_embeddings,
    _materialize_typicality_features,
    compute_reference_lr,
)
from core.latent_typicality.features import feature_columns_for_detectors
from core.latent_typicality.representations_utils import ORIGINAL_AUGMENTATION_TAG, build_sample_id


def _write_mini_representations(tmp_path: Path, *, with_augmentation: bool = False) -> Path:
    embed_dir = tmp_path / "embeddings"
    embed_dir.mkdir(parents=True)
    detectors = ("df_arena_1b", "sls_xlsr", "wedefense_wavlm_mhfa")
    rows: list[dict] = []
    for idx in range(20):
        y_fake = idx % 2
        label = "spoof" if y_fake else "bonafide"
        aug = "" if not with_augmentation or idx % 3 else "mp3_128k"
        sid = build_sample_id(
            dataset="SONAR",
            generator="xTTS",
            source_id=f"s{idx}",
            augmentation=aug or ORIGINAL_AUGMENTATION_TAG,
        )
        row = {
            "sample_id": sid,
            "dataset": "SONAR",
            "generator": "xTTS",
            "purpose": "reference_population",
            "reference_split": "reference_population",
            "label": label,
            "label_name": label,
            "y_spoof": y_fake,
            "source_id": f"s{idx}",
            "audio_path": str(tmp_path / f"{idx}.wav"),
            "augmentation": aug or ORIGINAL_AUGMENTATION_TAG,
            "error": "",
        }
        for det in detectors:
            emb = np.random.randn(8).astype(np.float32)
            emb_path = embed_dir / f"{sid}__{det}.npy"
            np.save(emb_path, emb)
            row[f"{det}_bonafide_logit"] = float(idx * 0.01)
            row[f"{det}_embedding_path"] = str(emb_path)
            row[f"{det}_embedding_dim"] = 8
        rows.append(row)
    out = tmp_path / "representations.csv"
    pd.DataFrame(rows).to_csv(out, index=False)
    return out


def test_cache_key_includes_latent_typicality(tmp_path: Path):
    matrix = tmp_path / "matrix.csv"
    matrix.write_text("sample_id,label,y_spoof\n", encoding="utf-8")
    items = [PopulationItem("SONAR", "xTTS")]
    roles = ReferenceSelectionRoles(tuple(items), tuple(items))
    base = _cache_key(
        score_matrix=matrix,
        roles=roles,
        selected_detectors=("df_arena_1b",),
        classifier="logistic",
        seed=1,
        use_latent_typicality=False,
    )
    latent = _cache_key(
        score_matrix=matrix,
        roles=roles,
        selected_detectors=("df_arena_1b",),
        classifier="logistic",
        seed=1,
        use_latent_typicality=True,
    )
    assert base != latent


def test_filter_matrix_scope_original_only():
    df = pd.DataFrame(
        {
            "augmentation": ["", ORIGINAL_AUGMENTATION_TAG, "mp3_128k"],
            "value": [1, 2, 3],
        }
    )
    filtered = _filter_matrix_scope(df, augmented_reference=False)
    assert len(filtered) == 2
    assert "mp3_128k" not in filtered["augmentation"].tolist()


def test_typicality_refs_built_from_train_only(tmp_path: Path):
    rep = _write_mini_representations(tmp_path)
    df = pd.read_csv(rep)
    df["y_fake"] = df["y_spoof"].astype(int)
    train = df.iloc[:6].copy()
    train.loc[:2, "y_fake"] = 0
    train.loc[3:, "y_fake"] = 1
    refs = _build_typicality_refs(
        train,
        ("df_arena_1b",),
        k=2,
        distance="euclidean",
    )
    assert "df_arena_1b" in refs
    assert refs["df_arena_1b"].k == 2


def test_filter_rows_with_embeddings_drops_orphans(tmp_path: Path):
    embed_dir = tmp_path / "embeddings"
    embed_dir.mkdir()
    sid_ok = build_sample_id(
        dataset="DFADD", generator="NaturalSpeech2", source_id="ok", augmentation=ORIGINAL_AUGMENTATION_TAG
    )
    sid_bad = build_sample_id(
        dataset="DFADD", generator="NaturalSpeech2", source_id="bad", augmentation="noise_snr_15"
    )
    detectors = ("df_arena_1b", "sls_xlsr", "wedefense_wavlm_mhfa")
    rows = []
    for sid in (sid_ok, sid_bad):
        row = {"sample_id": sid}
        for det in detectors:
            emb_path = embed_dir / f"{sid}__{det}.npy"
            if sid == sid_ok:
                np.save(emb_path, np.zeros(4, dtype=np.float32))
            row[f"{det}_embedding_path"] = str(emb_path)
        rows.append(row)
    df = pd.DataFrame(rows)
    filtered = _filter_rows_with_embeddings(df)
    assert len(filtered) == 1
    assert filtered.iloc[0]["sample_id"] == sid_ok


def test_compute_reference_lr_typicality_smoke(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    rep = _write_mini_representations(tmp_path)
    monkeypatch.setattr(
        "core.audio_spoofing_lr_reference.DEFAULT_REPRESENTATIONS_MATRIX",
        rep,
    )
    monkeypatch.setattr(
        "core.audio_spoofing_lr_reference.SAMPLE_PER_CLASS",
        5,
    )
    monkeypatch.setattr(
        "core.audio_spoofing_lr_reference.TRAIN_PER_CLASS",
        2,
    )
    monkeypatch.setattr(
        "core.audio_spoofing_lr_reference.CALIB_PER_CLASS",
        1,
    )
    monkeypatch.setattr(
        "core.audio_spoofing_lr_reference.TEST_PER_CLASS",
        2,
    )
    monkeypatch.setattr(
        "core.audio_spoofing_lr_reference.TYPICALITY_K",
        1,
    )
    detectors = ("df_arena_1b", "sls_xlsr", "wedefense_wavlm_mhfa")
    detector_scores = {}
    for det in detectors:
        detector_scores[det] = {
            "bonafide_logit": 0.1,
            "embedding": np.random.randn(8).astype(np.float32),
        }
    out_dir = tmp_path / "lr_out"
    report = compute_reference_lr(
        detector_scores=detector_scores,
        selection=[PopulationItem("SONAR", "xTTS")],
        out_dir=out_dir,
        selected_detectors=detectors,
        use_latent_typicality=True,
        sample_multiplier=1,
    )
    assert report.get("latent_typicality") is True
    cols = feature_columns_for_detectors("D", detectors)
    assert len(cols) == 18
