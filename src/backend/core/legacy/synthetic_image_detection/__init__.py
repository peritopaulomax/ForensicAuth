"""Detecção de imagens sintéticas (ensemble CNN + FFT + Effort)."""

from core.legacy.synthetic_image_detection.pipeline import run_synthetic_image_detection_analysis
from core.legacy.synthetic_image_detection.runtime import runtime_status

__all__ = ["runtime_status", "run_synthetic_image_detection_analysis"]
