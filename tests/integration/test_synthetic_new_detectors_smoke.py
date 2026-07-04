"""Smoke tests for newly integrated synthetic image detectors."""

from __future__ import annotations

import math

import pytest
import torch
from PIL import Image


def _device() -> torch.device:
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def test_fsd_real_inference_smoke():
    from core.legacy.fsd.fsd_pipeline import infer_fsd_from_pil
    from core.legacy.fsd.fsd_runtime import fsd_runtime_status

    ok, reason = fsd_runtime_status()
    if not ok:
        pytest.skip(reason)

    result = infer_fsd_from_pil(Image.new("RGB", (256, 256), (120, 80, 200)), _device())
    assert isinstance(float(result.z_score), float)
    assert result.threshold == pytest.approx(-2.0)


def test_universal_fake_detect_real_inference_smoke():
    from core.legacy.universal_fake_detect.ufd_pipeline import infer_ufd_from_pil
    from core.legacy.universal_fake_detect.ufd_runtime import ufd_runtime_status

    ok, reason = ufd_runtime_status()
    if not ok:
        pytest.skip(reason)

    probability = infer_ufd_from_pil(Image.new("RGB", (256, 256), (120, 80, 200)), _device())
    assert 0.0 <= probability <= 1.0


def test_grip_clipd_real_inference_smoke():
    from core.legacy.truebees_clip_d.clipd_pipeline import infer_clipd_from_pil
    from core.legacy.truebees_clip_d.clipd_runtime import clipd_runtime_status

    ok, reason = clipd_runtime_status()
    if not ok:
        pytest.skip(reason)

    llr = infer_clipd_from_pil(Image.new("RGB", (256, 256), (120, 80, 200)), _device())
    assert math.isfinite(llr)

