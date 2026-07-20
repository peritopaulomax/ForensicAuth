"""Unit tests for repair_representations_scores.repair_frame.

Covers the two invariants required so latent-typicality calibration never sees NaN:
- NaN detector scores in legitimate rows are backfilled from the sanitized score
  matrix by (dataset, generator, label, source_id_stem); the value is exact because
  the detector score is a property of the physical audio file.
- Orphan generator groups (present in representations but absent from the score
  matrix) are dropped entirely (originals + augmentations).
- Idempotency: re-running on an already-clean frame changes nothing.
"""

from __future__ import annotations

import csv

import numpy as np
import pandas as pd

from audio_lr_completion_gate import check_representations_integrity
from repair_representations_scores import (
    LOGIT_COLS,
    SCORE_COLS,
    _build_matrix_lookup,
    repair_frame,
)


def _matrix_row(dataset, generator, label, source_id, logits):
    row = {
        "dataset": dataset,
        "generator": generator,
        "label": label,
        "source_id": source_id,
        "error": "",
    }
    for det_suffix, val in zip(SCORE_COLS, _expand(logits)):
        row[det_suffix] = val
    return row


def _expand(logits):
    # Each detector contributes (bonafide_logit, bonafide_prob, spoof_logit).
    out = []
    for lg in logits:
        out += [lg, 0.5, -lg]
    return out


def _rep_row(dataset, generator, label, source_id, logits, *, aug="original"):
    row = {
        "dataset": dataset,
        "generator": generator,
        "label": label,
        "source_id": source_id,
        "augmentation": aug,
        "df_arena_1b_embedding_path": "x.npy",
    }
    for det_suffix, val in zip(SCORE_COLS, _expand(logits)):
        row[det_suffix] = val
    return row


def _make_matrix():
    m = pd.DataFrame(
        [
            _matrix_row("DS", "genA", "spoof", "s1", (1.0, 0.5, 0.2)),
            _matrix_row("DS", "genA", "bonafide", "b1", (0.1, 0.2, 0.3)),
        ]
    )
    lookup = _build_matrix_lookup(m)
    groups = set(zip(m["dataset"].astype(str), m["generator"].astype(str)))
    return lookup, groups


def test_backfill_nan_scores_from_matrix():
    lookup, groups = _make_matrix()
    nan = (float("nan"),) * 3
    rep = pd.DataFrame(
        [
            _rep_row("DS", "genA", "spoof", "s1", nan),  # NaN -> backfill from matrix
            _rep_row("DS", "genA", "bonafide", "b1", (0.1, 0.2, 0.3)),  # already finite
        ]
    )
    res = repair_frame(rep, lookup, groups)
    out = res["frame"]
    assert res["backfilled_rows"] == 1
    assert res["orphan_rows_removed"] == 0
    assert res["unresolved_keys"] == []
    vals = out[LOGIT_COLS].to_numpy(dtype=float)
    assert np.isfinite(vals).all()
    # backfilled row got the matrix bonafide_logit for det0 (1.0)
    fixed = out[out["source_id"] == "s1"].iloc[0]
    assert fixed["df_arena_1b_bonafide_logit"] == 1.0


def test_orphan_generator_group_removed():
    lookup, groups = _make_matrix()
    nan = (float("nan"),) * 3
    rep = pd.DataFrame(
        [
            _rep_row("DS", "genA", "spoof", "s1", (1.0, 0.5, 0.2)),
            # orphan group: generator not in the score matrix -> all rows dropped
            _rep_row("DS", "orphan", "spoof", "z9", nan, aug="original"),
            _rep_row("DS", "orphan", "spoof", "z9", nan, aug="mp3_128k"),
        ]
    )
    res = repair_frame(rep, lookup, groups)
    out = res["frame"]
    assert ["DS", "orphan"] in [list(g) for g in res["orphan_groups"]]
    assert res["orphan_rows_removed"] == 2
    assert (out["generator"] == "orphan").sum() == 0
    assert res["unresolved_keys"] == []
    assert np.isfinite(out[LOGIT_COLS].to_numpy(dtype=float)).all()


def test_idempotent_on_clean_frame():
    lookup, groups = _make_matrix()
    rep = pd.DataFrame(
        [
            _rep_row("DS", "genA", "spoof", "s1", (1.0, 0.5, 0.2)),
            _rep_row("DS", "genA", "bonafide", "b1", (0.1, 0.2, 0.3)),
        ]
    )
    first = repair_frame(rep, lookup, groups)["frame"]
    second_res = repair_frame(first, lookup, groups)
    assert second_res["backfilled_rows"] == 0
    assert second_res["orphan_rows_removed"] == 0
    pd.testing.assert_frame_equal(
        first.reset_index(drop=True), second_res["frame"].reset_index(drop=True)
    )


DETECTORS = ("df_arena_1b", "sls_xlsr", "wedefense_wavlm_mhfa")


def _write_csv(path, rows):
    fieldnames = []
    for r in rows:
        for k in r:
            if k not in fieldnames:
                fieldnames.append(k)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def _gate_row(dataset, generator, label, source_id, logits):
    row = {"dataset": dataset, "generator": generator, "label": label, "source_id": source_id, "error": ""}
    for det, val in zip(DETECTORS, logits):
        row[f"{det}_bonafide_logit"] = val
    return row


def test_gate_representations_integrity_clean(tmp_path):
    matrix = tmp_path / "matrix.csv"
    rep = tmp_path / "rep.csv"
    _write_csv(matrix, [_gate_row("DS", "genA", "spoof", "s1", (1.0, 0.5, 0.2))])
    _write_csv(rep, [_gate_row("DS", "genA", "spoof", "s1", (1.0, 0.5, 0.2))])
    res = check_representations_integrity(rep, matrix)
    assert res["ok"] is True
    assert res["nan_logit_rows"] == 0
    assert res["orphan_groups"] == []


def test_gate_representations_integrity_rejects_nan(tmp_path):
    matrix = tmp_path / "matrix.csv"
    rep = tmp_path / "rep.csv"
    _write_csv(matrix, [_gate_row("DS", "genA", "spoof", "s1", (1.0, 0.5, 0.2))])
    _write_csv(rep, [_gate_row("DS", "genA", "spoof", "s1", (1.0, "", 0.2))])
    res = check_representations_integrity(rep, matrix)
    assert res["ok"] is False
    assert res["nan_logit_rows"] == 1


def test_gate_representations_integrity_rejects_orphan_group(tmp_path):
    matrix = tmp_path / "matrix.csv"
    rep = tmp_path / "rep.csv"
    _write_csv(matrix, [_gate_row("DS", "genA", "spoof", "s1", (1.0, 0.5, 0.2))])
    _write_csv(rep, [
        _gate_row("DS", "genA", "spoof", "s1", (1.0, 0.5, 0.2)),
        _gate_row("DS", "orphan", "spoof", "z9", (1.0, 0.5, 0.2)),
    ])
    res = check_representations_integrity(rep, matrix)
    assert res["ok"] is False
    assert ["DS", "orphan"] in res["orphan_groups"]
