"""Helpers compartilhados pelos plugins de audio forense."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Dict, Generator, TypeVar

from core.job_staging import job_artifact_dir_unique
from core.legacy.audio.audio_prepare import prepare_wav_for_analysis, safe_unlink

T = TypeVar("T")


@contextmanager
def prepared_audio_path(
    evidence_path: str,
    parameters: Dict[str, Any],
    *,
    dest_path: Path | None = None,
) -> Generator[str, None, None]:
    stereo_diff = bool(parameters.get("stereo_diff", False))
    wav_path, tmp = prepare_wav_for_analysis(
        evidence_path, stereo_diff=stereo_diff, dest_path=dest_path
    )
    try:
        yield wav_path
    finally:
        safe_unlink(tmp)


def job_result_dir(evidence_path: str, technique: str, parameters: Dict[str, Any] | None = None) -> Path:
    return job_artifact_dir_unique(
        parameters or {},
        fallback_subdir=technique,
        evidence_path=evidence_path,
    )


def run_legacy(
    evidence_path: str,
    parameters: Dict[str, Any],
    technique: str,
    fn: Callable[[str, Path], T],
) -> T:
    result_dir = job_result_dir(evidence_path, technique, parameters)
    result_dir.mkdir(parents=True, exist_ok=True)
    prepared_dest = result_dir / "prepared_audio.wav"
    with prepared_audio_path(
        evidence_path, parameters, dest_path=prepared_dest
    ) as wav_path:
        return fn(wav_path, result_dir)
