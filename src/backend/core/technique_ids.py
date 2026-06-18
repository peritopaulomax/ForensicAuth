"""Identificadores canônicos de técnicas e aliases legados (jobs antigos no banco)."""

from __future__ import annotations

# Técnica: detecção de imagens sintéticas (ensemble Gradio CNN + FFT + Effort).
SYNTHETIC_IMAGE_DETECTION = "synthetic_image_detection"

TECHNIQUE_ALIASES: dict[str, str] = {
    "sepael": SYNTHETIC_IMAGE_DETECTION,
}


def resolve_technique_id(technique: str) -> str:
    """Normaliza ID de técnica (ex.: jobs gravados com nome legado)."""
    return TECHNIQUE_ALIASES.get(technique, technique)
