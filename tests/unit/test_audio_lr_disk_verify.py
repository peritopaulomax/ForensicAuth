"""Unit tests for disk verification and completion gate logic."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from audio_lr_disk_verify import (
    TARGET_PER_CLASS,
    SubgroupAudit,
    _record_gaps,
    read_scores_sidecar,
    write_scores_sidecar,
)


def test_write_and_read_scores_sidecar(tmp_path: Path) -> None:
    sample_id = "ASVspoof5__flac_E_eval__E_0001858027__mp3_128k"
    row = {
        "df_arena_1b_bonafide_logit": 1.0,
        "df_arena_1b_spoof_logit": -1.0,
        "df_arena_1b_bonafide_prob": 0.7,
        "sls_xlsr_bonafide_logit": 0.5,
        "sls_xlsr_spoof_logit": -0.5,
        "sls_xlsr_bonafide_prob": 0.6,
        "wedefense_wavlm_mhfa_bonafide_logit": 0.2,
        "wedefense_wavlm_mhfa_spoof_logit": -0.2,
        "wedefense_wavlm_mhfa_bonafide_prob": 0.55,
    }
    path = write_scores_sidecar(tmp_path, sample_id, row)
    assert path.is_file()
    assert read_scores_sidecar(path)


def test_subgroup_audit_passes_at_target() -> None:
    audit = SubgroupAudit(dataset="ASVspoof5", generator="flac_E_eval")
    audit.target_bf_orig = TARGET_PER_CLASS
    audit.target_sp_orig = TARGET_PER_CLASS
    audit.target_bf_aug = TARGET_PER_CLASS * 4
    audit.target_sp_aug = TARGET_PER_CLASS * 4
    audit.target_units = 5000

    for bucket, target in (
        (audit.orig_bonafide, TARGET_PER_CLASS),
        (audit.orig_spoof, TARGET_PER_CLASS),
        (audit.aug_bonafide, TARGET_PER_CLASS * 4),
        (audit.aug_spoof, TARGET_PER_CLASS * 4),
    ):
        bucket.wav = target
        bucket.emb_complete = target
        bucket.scores = target
        bucket.complete_units = target

    _record_gaps(audit)
    assert audit.passed
    assert audit.units_ok == 5000


def test_subgroup_audit_detects_gap() -> None:
    audit = SubgroupAudit(dataset="SONAR", generator="VALLE")
    audit.orig_bonafide.complete_units = 500
    audit.orig_spoof.complete_units = 200
    audit.aug_bonafide.complete_units = 2000
    audit.aug_spoof.complete_units = 300
    _record_gaps(audit)
    assert not audit.passed
    assert any(g["field"] == "sp_orig_complete_units" for g in audit.gaps)
