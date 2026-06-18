"""Persistencia e consulta de metadados tecnicos de audio em evidencias."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from sqlalchemy.orm import Session

from core.legacy.audio.audio_probe import probe_audio_metadata
from models.evidence import Evidence

AUDIO_TECHNICAL_KEY = "audio_technical"


def get_audio_technical_metadata(evidence: Evidence) -> Dict[str, Any] | None:
    meta = evidence.extra_metadata or {}
    stored = meta.get(AUDIO_TECHNICAL_KEY)
    return stored if isinstance(stored, dict) else None


def ensure_audio_technical_metadata(evidence: Evidence, db: Session) -> Dict[str, Any]:
    """Retorna metadados em cache ou sonda o arquivo e persiste em extra_metadata."""
    cached = get_audio_technical_metadata(evidence)
    if cached:
        return cached

    file_path = Path(evidence.file_path)
    if not file_path.is_file():
        return {}

    technical = probe_audio_metadata(str(file_path))
    if not technical:
        return {}

    meta = dict(evidence.extra_metadata or {})
    meta[AUDIO_TECHNICAL_KEY] = technical
    evidence.extra_metadata = meta
    db.add(evidence)
    db.commit()
    db.refresh(evidence)
    return technical


def probe_audio_for_upload(file_path: str) -> Dict[str, Any]:
    """Sonda metadados no upload (sem persistir — chamado antes do commit)."""
    return probe_audio_metadata(file_path)
