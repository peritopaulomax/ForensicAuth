"""Resolve Celery queue for forensic analysis jobs."""

from __future__ import annotations

from core.gpu_inference import ML_GPU_TECHNIQUES

CPU_QUEUE = "celery"
GPU_QUEUE = "gpu"


def queue_for_technique(technique: str) -> str:
    if technique in ML_GPU_TECHNIQUES:
        return GPU_QUEUE
    return CPU_QUEUE
