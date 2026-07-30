"""ViLocal — video inpainting localization with contrastive learning (IEEE SPL 2025)."""

from forensics.vilocal.vilocal_pipeline import run_vilocal_analysis, write_vilocal_report
from forensics.vilocal.vilocal_runtime import vilocal_runtime_status

__all__ = [
    "vilocal_runtime_status",
    "run_vilocal_analysis",
    "write_vilocal_report",
]
