"""Unit tests for audio LR dataset utilities."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
import sys

sys.path.insert(0, str(SCRIPTS))

from audio_lr_dataset_utils import (  # noqa: E402
    assign_purpose_splits,
    infer_generator,
    label_to_y_spoof,
    read_protocol_csv,
    resolve_audio_path,
    sample_balanced,
)


def test_label_to_y_spoof():
    assert label_to_y_spoof("spoof") == 1
    assert label_to_y_spoof("bonafide") == 0


def test_infer_generator_dfadd():
    row = {
        "dataset": "DFADD",
        "subset": "test_converted2",
        "file_path": "/x/test_converted2/wav/p227_164_GradTTS.flac",
    }
    assert infer_generator(row) == "GradTTS"


def test_infer_generator_codecfake():
    row = {"dataset": "CodecFake", "subset": "C3", "file_path": "/x/C3/file.wav"}
    assert infer_generator(row) == "C3"


def test_resolve_audio_path_prefix():
    config = {"path_prefixes": [{"remote": "/remote", "local": "/local"}]}
    assert resolve_audio_path("/remote/a.wav", config) == Path("/local/a.wav")


def test_sample_balanced_from_protocol(tmp_path):
    csv_path = tmp_path / "proto.csv"
    rows = []
    for idx in range(200):
        rows.append(
            {
                "file_path": f"/data/f{idx}.wav",
                "label": "bonafide" if idx % 2 == 0 else "spoof",
                "dataset": "CodecFake",
                "subset": "C1",
                "original_csv": "x.csv",
                "status": "ok",
            }
        )
    pd.DataFrame(rows).to_csv(csv_path, index=False)
    df = read_protocol_csv(csv_path, datasets=["CodecFake"], subsets=["C1"])
    sampled = sample_balanced(df, per_class=10, seed=42)
    assert len(sampled) == 20
    assert sampled["y_spoof"].value_counts().to_dict() == {0: 10, 1: 10}


def test_assign_purpose_splits_counts():
    df = pd.DataFrame(
        {
            "dataset": ["CodecFake"] * 300,
            "generator": ["C1"] * 300,
            "label": ["bonafide"] * 150 + ["spoof"] * 150,
            "y_spoof": [0] * 150 + [1] * 150,
        }
    )
    split = assign_purpose_splits(
        df,
        train_per_class=75,
        calib_per_class=38,
        test_per_class=37,
        seed=1,
    )
    assert len(split) == 300
    assert split["purpose"].value_counts().to_dict() == {
        "calibration_train": 150,
        "calibration_bigauss": 76,
        "evaluation": 74,
    }
