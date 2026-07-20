"""Tests for Fake-or-Real protocol rebuild."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from fix_fake_or_real_protocol import build_fake_or_real_rows  # noqa: E402


def test_build_fake_or_real_rows_labels_follow_folders(tmp_path: Path):
    testing = tmp_path / "Speech_DF_Arena/AntiSpoofing-Datasets/for-norm/testing"
    (testing / "real").mkdir(parents=True)
    (testing / "fake").mkdir(parents=True)
    (testing / "real" / "file1.wav").write_bytes(b"r")
    (testing / "fake" / "file2.wav").write_bytes(b"f")

    rows = build_fake_or_real_rows(
        local_bases_root=tmp_path,
        remote_bases_root="/remote",
    )
    assert len(rows) == 2
    real_row = rows[rows["label"] == "bonafide"].iloc[0]
    fake_row = rows[rows["label"] == "spoof"].iloc[0]
    assert "/testing/real/file1.wav" in real_row["file_path"]
    assert "/testing/fake/file2.wav" in fake_row["file_path"]
    assert real_row["dataset"] == "Fake-or-Real"
    assert fake_row["original_csv"] == "fake_or_real.csv"
