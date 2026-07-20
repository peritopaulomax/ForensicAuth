"""Integration test for physical completion gate."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "scripts" / "audio_lr_completion_gate.py"
REPORT = ROOT / "outputs/lr_calibration/audio_spoofing/inventory/completion_gate_report.json"


def test_completion_gate_report_schema() -> None:
    """Gate must produce structured report (pass or fail)."""
    proc = subprocess.run(
        [sys.executable, str(GATE)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": f"{ROOT / 'scripts'}:{ROOT / 'src' / 'backend'}"},
    )
    assert REPORT.is_file(), proc.stderr or proc.stdout
    data = json.loads(REPORT.read_text(encoding="utf-8"))
    assert "by_generator" in data
    assert "eligible_pct" in data
    assert "global_pct" in data
    for gen in data["by_generator"]:
        assert "dataset" in gen
        assert "generator" in gen
        assert "pct" in gen
        assert "bf_orig" in gen


@pytest.mark.skipif(
    os.environ.get("AUDIO_LR_GATE_REQUIRE_PASS") != "1",
    reason="Set AUDIO_LR_GATE_REQUIRE_PASS=1 when population is complete",
)
def test_completion_gate_passes_when_complete() -> None:
    proc = subprocess.run(
        [sys.executable, str(GATE)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": f"{ROOT / 'scripts'}:{ROOT / 'src' / 'backend'}"},
    )
    if proc.returncode != 0:
        data = json.loads(REPORT.read_text(encoding="utf-8"))
        failing = [g for g in data.get("by_generator", []) if not g.get("passed")]
        pytest.fail(
            f"Gate failed ({data.get('eligible_pct')}% eligible). "
            f"First gaps: {failing[:3]}"
        )
