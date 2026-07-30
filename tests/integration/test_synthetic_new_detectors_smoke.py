"""Smoke tests for synthetic image detectors that require local weights/GPU."""

from __future__ import annotations

import math

import pytest
import torch
from PIL import Image


pytestmark = [pytest.mark.weights, pytest.mark.gpu]


def _device() -> torch.device:
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def test_grip_clipd_real_inference_smoke():
    from forensics.truebees_clip_d.clipd_pipeline import infer_clipd_from_pil
    from forensics.truebees_clip_d.clipd_runtime import clipd_runtime_status

    ok, reason = clipd_runtime_status()
    if not ok:
        pytest.skip(reason)

    llr = infer_clipd_from_pil(Image.new("RGB", (256, 256), (120, 80, 200)), _device())
    assert math.isfinite(llr)
