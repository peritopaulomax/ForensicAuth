"""Tests for job preview cleanup (canonical nested + legacy flat layouts)."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest


def _write_preview(job_dir: Path, *, preview: bool = True, age_days: int = 10) -> Path:
    job_dir.mkdir(parents=True, exist_ok=True)
    result_path = job_dir / "result.json"
    result_path.write_text(
        json.dumps({"preview": preview, "promoted": False, "ok": True}),
        encoding="utf-8",
    )
    (job_dir / "heatmap.png").write_bytes(b"png")
    stamp = (datetime.now(timezone.utc) - timedelta(days=age_days)).timestamp()
    os.utime(result_path, (stamp, stamp))
    return result_path


def test_cleanup_removes_nested_canonical_preview(tmp_path: Path, monkeypatch):
    from core.preview_cleanup import cleanup_expired_job_previews

    case_id = uuid.uuid4()
    evidence_id = uuid.uuid4()
    job_id = uuid.uuid4()
    job_dir = tmp_path / str(case_id) / str(evidence_id) / str(job_id)
    _write_preview(job_dir, age_days=10)

    settings = SimpleNamespace(RESULTS_DIR=str(tmp_path), JOB_PREVIEW_RETENTION_DAYS=7)
    monkeypatch.setattr("core.preview_cleanup.get_settings", lambda: settings)

    assert cleanup_expired_job_previews() == 1
    assert not job_dir.exists()
    # Empty parents pruned
    assert not (tmp_path / str(case_id) / str(evidence_id)).exists()
    assert not (tmp_path / str(case_id)).exists()


def test_cleanup_keeps_fresh_nested_preview(tmp_path: Path, monkeypatch):
    from core.preview_cleanup import cleanup_expired_job_previews

    case_id = uuid.uuid4()
    evidence_id = uuid.uuid4()
    job_id = uuid.uuid4()
    job_dir = tmp_path / str(case_id) / str(evidence_id) / str(job_id)
    _write_preview(job_dir, age_days=1)

    settings = SimpleNamespace(RESULTS_DIR=str(tmp_path), JOB_PREVIEW_RETENTION_DAYS=7)
    monkeypatch.setattr("core.preview_cleanup.get_settings", lambda: settings)

    assert cleanup_expired_job_previews() == 0
    assert job_dir.exists()


def test_cleanup_removes_legacy_flat_preview(tmp_path: Path, monkeypatch):
    from core.preview_cleanup import cleanup_expired_job_previews

    job_dir = tmp_path / str(uuid.uuid4())
    _write_preview(job_dir, age_days=10)

    settings = SimpleNamespace(RESULTS_DIR=str(tmp_path), JOB_PREVIEW_RETENTION_DAYS=7)
    monkeypatch.setattr("core.preview_cleanup.get_settings", lambda: settings)

    assert cleanup_expired_job_previews() == 1
    assert not job_dir.exists()


def test_cleanup_skips_explicit_non_preview_result_json(tmp_path: Path, monkeypatch):
    from core.preview_cleanup import cleanup_expired_job_previews

    job_dir = tmp_path / str(uuid.uuid4())
    _write_preview(job_dir, preview=False, age_days=30)

    settings = SimpleNamespace(RESULTS_DIR=str(tmp_path), JOB_PREVIEW_RETENTION_DAYS=7)
    monkeypatch.setattr("core.preview_cleanup.get_settings", lambda: settings)

    assert cleanup_expired_job_previews() == 0
    assert job_dir.exists()


def test_cleanup_removes_legacy_result_json_without_preview_flag(tmp_path: Path, monkeypatch):
    from core.preview_cleanup import cleanup_expired_job_previews

    job_dir = tmp_path / str(uuid.uuid4())
    job_dir.mkdir(parents=True)
    result_path = job_dir / "result.json"
    result_path.write_text(json.dumps({"ok": True}), encoding="utf-8")
    stamp = (datetime.now(timezone.utc) - timedelta(days=10)).timestamp()
    os.utime(result_path, (stamp, stamp))

    settings = SimpleNamespace(RESULTS_DIR=str(tmp_path), JOB_PREVIEW_RETENTION_DAYS=7)
    monkeypatch.setattr("core.preview_cleanup.get_settings", lambda: settings)

    assert cleanup_expired_job_previews() == 1
    assert not job_dir.exists()


def test_cleanup_removes_technique_fallback_tmp_dir(tmp_path: Path, monkeypatch):
    from core.preview_cleanup import cleanup_expired_job_previews

    tmp_dir = tmp_path / "ela"
    tmp_dir.mkdir()
    artifact = tmp_dir / "out.png"
    artifact.write_bytes(b"png")
    stamp = (datetime.now(timezone.utc) - timedelta(days=10)).timestamp()
    os.utime(artifact, (stamp, stamp))
    os.utime(tmp_dir, (stamp, stamp))

    settings = SimpleNamespace(RESULTS_DIR=str(tmp_path), JOB_PREVIEW_RETENTION_DAYS=7)
    monkeypatch.setattr("core.preview_cleanup.get_settings", lambda: settings)

    assert cleanup_expired_job_previews() == 1
    assert not tmp_dir.exists()


def test_retention_zero_keeps_fresh_within_grace(tmp_path: Path, monkeypatch):
    from core.preview_cleanup import cleanup_expired_job_previews

    job_dir = tmp_path / str(uuid.uuid4())
    _write_preview(job_dir, age_days=0)  # mtime ~ now (within 1h grace)

    settings = SimpleNamespace(RESULTS_DIR=str(tmp_path), JOB_PREVIEW_RETENTION_DAYS=0)
    monkeypatch.setattr("core.preview_cleanup.get_settings", lambda: settings)

    assert cleanup_expired_job_previews() == 0
    assert job_dir.exists()


def test_purge_all_previews(tmp_path: Path, monkeypatch):
    from core.preview_cleanup import purge_all_previews

    (tmp_path / "ela").mkdir()
    (tmp_path / "ela" / "x.bin").write_bytes(b"1")
    nested = tmp_path / str(uuid.uuid4()) / str(uuid.uuid4()) / str(uuid.uuid4())
    nested.mkdir(parents=True)
    (nested / "result.json").write_text("{}", encoding="utf-8")
    (tmp_path / "stray.txt").write_text("x", encoding="utf-8")

    settings = SimpleNamespace(RESULTS_DIR=str(tmp_path), JOB_PREVIEW_RETENTION_DAYS=0)
    monkeypatch.setattr("core.preview_cleanup.get_settings", lambda: settings)

    assert purge_all_previews() == 3
    assert list(tmp_path.iterdir()) == []


def test_cleanup_via_db_uses_result_path(tmp_path: Path, monkeypatch):
    from core.preview_cleanup import cleanup_expired_job_previews

    case_id = uuid.uuid4()
    evidence_id = uuid.uuid4()
    job_id = uuid.uuid4()
    job_dir = tmp_path / str(case_id) / str(evidence_id) / str(job_id)
    _write_preview(job_dir, age_days=10)

    evidence = SimpleNamespace(case_id=case_id, id=evidence_id)
    job = SimpleNamespace(
        id=job_id,
        evidence_id=evidence_id,
        evidence=evidence,
        status="completed",
        completed_at=datetime.now(timezone.utc) - timedelta(days=10),
        result_path=str(job_dir),
    )

    class _Query:
        def options(self, *_a, **_k):
            return self

        def filter(self, *_a, **_k):
            return self

        def all(self):
            return [job]

    class _Db:
        def query(self, *_a, **_k):
            return _Query()

    settings = SimpleNamespace(RESULTS_DIR=str(tmp_path), JOB_PREVIEW_RETENTION_DAYS=7)
    monkeypatch.setattr("core.preview_cleanup.get_settings", lambda: settings)

    assert cleanup_expired_job_previews(_Db()) == 1
    assert not job_dir.exists()


def test_retention_zero_removes_all_completed_previews(tmp_path: Path, monkeypatch):
    from core.preview_cleanup import cleanup_expired_job_previews

    job_dir = tmp_path / str(uuid.uuid4())
    _write_preview(job_dir, age_days=1)

    settings = SimpleNamespace(RESULTS_DIR=str(tmp_path), JOB_PREVIEW_RETENTION_DAYS=0)
    monkeypatch.setattr("core.preview_cleanup.get_settings", lambda: settings)

    assert cleanup_expired_job_previews() == 1
    assert not job_dir.exists()


def test_scheduler_run_once_opens_db(monkeypatch):
    from core import preview_cleanup_scheduler as sched

    calls: list[object] = []

    class _FakeSession:
        def close(self):
            calls.append("close")

    monkeypatch.setattr(
        "app.database.SessionLocal",
        lambda: _FakeSession(),
    )

    def _fake_cleanup(db=None):
        calls.append(db)
        return 3

    monkeypatch.setattr(sched, "cleanup_expired_job_previews", _fake_cleanup)
    assert sched.run_preview_cleanup_once() == 3
    assert any(c != "close" and c is not None for c in calls)
    assert "close" in calls
