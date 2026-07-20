"""Unit tests for the audio LR sanitization invariants.

Covers:
- sanitize_audio_lr: dedup by (dataset, generator, label, source_id) keeping the
  complete row, moving NaN/placeholder rows to a worklist, recording error rows.
- run_audio_spoofing_score_matrix: finite-score resume identity (shared bonafide
  pools reused across generators are kept, NaN rows are dropped, path is not the key).
- audio_lr_completion_gate.check_matrix_integrity: rejects NaN, duplicates, errors.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd

from audio_lr_completion_gate import check_matrix_integrity
from run_audio_spoofing_score_matrix import _identity, _row_has_finite_scores
from sanitize_audio_lr import sanitize

DETECTORS = ("df_arena_1b", "sls_xlsr", "wedefense_wavlm_mhfa")


def _row(dataset, generator, label, source_id, logits, *, error="", audio_path="x", aug=""):
    row = {
        "dataset": dataset,
        "generator": generator,
        "label": label,
        "source_id": source_id,
        "augmentation": aug,
        "audio_path": audio_path,
        "error": error,
    }
    for det, val in zip(DETECTORS, logits):
        row[f"{det}_bonafide_logit"] = val
        row[f"{det}_spoof_logit"] = 0.0 if val != "" else ""
    return row


def _write_matrix(path: Path, rows: list[dict]) -> None:
    fieldnames: list[str] = []
    for r in rows:
        for k in r:
            if k not in fieldnames:
                fieldnames.append(k)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def test_sanitize_dedups_and_purges_nan(tmp_path: Path) -> None:
    matrix = tmp_path / "m.csv"
    rows = [
        _row("ASVspoof5", "flac_E_eval", "spoof", "E1", (1.0, 0.5, 0.2)),
        # duplicate complete of E1 -> dropped
        _row("ASVspoof5", "flac_E_eval", "spoof", "E1", (1.1, 0.6, 0.3)),
        # NaN row for a NEW source -> goes to worklist
        _row("ASVspoof5", "flac_E_eval", "spoof", "E2", ("", "", "")),
        # NaN row whose complete twin exists -> dropped as dup, not worklist
        _row("ASVspoof5", "flac_E_eval", "spoof", "E1", ("", "", "")),
        # error row -> recorded unusable, dropped from clean matrix
        _row("ASVspoof5", "flac_E_eval", "bonafide", "B1", ("", "", ""), error="RuntimeError: short"),
    ]
    _write_matrix(matrix, rows)

    result = sanitize(matrix)
    report = result["report"]

    assert report["complete_unique_rows"] == 1
    assert report["duplicate_complete_removed"] == 1
    assert report["nan_rows_to_rescore"] == 1
    assert report["nan_rows_dropped_as_dup"] == 1
    assert report["error_rows"] == 1

    clean = result["clean_df"]
    # Clean matrix keeps only the single complete unique row (no NaN, no error).
    assert len(clean) == 1
    assert clean.iloc[0]["source_id"] == "E1"

    worklist = result["worklist"]
    assert len(worklist) == 1
    assert worklist.iloc[0]["source_id"] == "E2"

    unusable = result["unusable"]
    assert len(unusable) == 1
    assert unusable.iloc[0]["source_id"] == "B1"


def test_row_has_finite_scores() -> None:
    assert _row_has_finite_scores(_row("d", "g", "spoof", "s", (1.0, 2.0, 3.0)))
    assert not _row_has_finite_scores(_row("d", "g", "spoof", "s", (1.0, "", 3.0)))
    assert not _row_has_finite_scores(_row("d", "g", "spoof", "s", ("nan", 2.0, 3.0)))


def test_identity_keeps_shared_bonafide_distinct() -> None:
    # Same bonafide file reused by two generators must have distinct identities
    # (path is NOT the dedup key), so shared pools are not collapsed on resume.
    a = _row("DFADD", "GradTTS", "bonafide", "p228", (1.0, 2.0, 3.0), audio_path="/shared/p228.wav")
    b = _row("DFADD", "matcha", "bonafide", "p228", (1.0, 2.0, 3.0), audio_path="/shared/p228.wav")
    assert _identity(a) != _identity(b)
    # Original vs augmentation of same id are distinct too.
    orig = _row("DFADD", "GradTTS", "bonafide", "p228", (1.0, 2.0, 3.0))
    aug = _row("DFADD", "GradTTS", "bonafide", "p228", (1.0, 2.0, 3.0), aug="mp3_128k")
    assert _identity(orig) != _identity(aug)


def test_gate_matrix_integrity_clean(tmp_path: Path) -> None:
    matrix = tmp_path / "m.csv"
    _write_matrix(matrix, [
        _row("ASVspoof5", "flac_E_eval", "spoof", "E1", (1.0, 0.5, 0.2)),
        _row("ASVspoof5", "flac_E_eval", "bonafide", "B1", (0.1, 0.2, 0.3)),
    ])
    integrity = check_matrix_integrity(matrix)
    assert integrity["ok"] is True
    assert integrity["nan_logit_rows"] == 0
    assert integrity["duplicate_rows"] == 0
    assert integrity["error_rows"] == 0


def test_gate_matrix_integrity_rejects_nan(tmp_path: Path) -> None:
    matrix = tmp_path / "m.csv"
    _write_matrix(matrix, [
        _row("ASVspoof5", "flac_E_eval", "spoof", "E1", (1.0, "", 0.2)),
    ])
    integrity = check_matrix_integrity(matrix)
    assert integrity["ok"] is False
    assert integrity["nan_logit_rows"] == 1


def test_gate_matrix_integrity_rejects_duplicates(tmp_path: Path) -> None:
    matrix = tmp_path / "m.csv"
    _write_matrix(matrix, [
        _row("ASVspoof5", "flac_E_eval", "spoof", "E1", (1.0, 0.5, 0.2)),
        _row("ASVspoof5", "flac_E_eval", "spoof", "E1", (1.1, 0.6, 0.3)),
    ])
    integrity = check_matrix_integrity(matrix)
    assert integrity["ok"] is False
    assert integrity["duplicate_rows"] == 2


def test_gate_matrix_integrity_rejects_errors(tmp_path: Path) -> None:
    matrix = tmp_path / "m.csv"
    _write_matrix(matrix, [
        _row("ASVspoof5", "flac_E_eval", "spoof", "E1", (1.0, 0.5, 0.2)),
        _row("ASVspoof5", "flac_E_eval", "bonafide", "B1", ("", "", ""), error="RuntimeError: short"),
    ])
    integrity = check_matrix_integrity(matrix)
    assert integrity["ok"] is False
    assert integrity["error_rows"] == 1
