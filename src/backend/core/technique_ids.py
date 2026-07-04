"""Identificadores canônicos de técnicas e aliases legados (jobs antigos no banco)."""

from __future__ import annotations

# Técnica: detecção de imagens sintéticas (ensemble Gradio CNN + FFT + Effort).
SYNTHETIC_IMAGE_DETECTION = "synthetic_image_detection"

# Técnica: detecção de ataques de apresentação facial (PAD).
PRESENTATION_ATTACK_DETECTION = "presentation_attack_detection"

# Técnica: detecção de spoofing de áudio via DF Arena 1B.
AUDIO_SPOOFING_DETECTION = "audio_spoofing_detection"

TECHNIQUE_ALIASES: dict[str, str] = {
    "sepael": SYNTHETIC_IMAGE_DETECTION,
}


def resolve_technique_id(technique: str) -> str:
    """Normaliza ID de técnica (ex.: jobs gravados com nome legado)."""
    return TECHNIQUE_ALIASES.get(technique, technique)
