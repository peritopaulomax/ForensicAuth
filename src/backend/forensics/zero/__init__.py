"""ZERO grid detection via libzero.so_ (Farid)."""

from forensics.zero.libzero_loader import zero_runtime_status
from forensics.zero.zero_pipeline import run_zero_analysis

__all__ = ["zero_runtime_status", "run_zero_analysis"]
