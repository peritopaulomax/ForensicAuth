"""JPEG Ghosts — Farid (IEEE TIFS 2009). Exposto via plugin forense."""

from core.legacy.jpeg_ghosts.jpeg_ghosts import (
    compute_metric,
    generate_shifted_images,
    process_image,
    process_single_quality,
    run_jpeg_ghosts_analysis,
)

__all__ = [
    "process_single_quality",
    "process_image",
    "compute_metric",
    "generate_shifted_images",
    "run_jpeg_ghosts_analysis",
]
