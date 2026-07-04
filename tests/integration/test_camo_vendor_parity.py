"""Integration: ForensicAuth CAMO score matches vendored BitMind CAMO."""

from __future__ import annotations

import sys

import numpy as np
import pytest
import torch
from PIL import Image


def _as_score(value: object) -> float:
    return float(np.asarray(value, dtype=np.float64).reshape(-1)[0])


@pytest.mark.integration
class TestCamoVendorParity:
    def test_forensicauth_score_matches_direct_vendor_call(self):
        from core.legacy.camo.camo_pipeline import clear_camo_model_cache, infer_camo_from_pil
        from core.legacy.camo.camo_runtime import any_camo_ready, camo_vendor_dir
        from core.legacy.camo.camo_vendor import bootstrap_camo_modules, camo_vendor_context

        ok, reason = any_camo_ready()
        if not ok:
            pytest.skip(reason)

        image = Image.new("RGB", (256, 256), color=(96, 128, 160))
        device = torch.device("cpu")

        with camo_vendor_context():
            bootstrap_camo_modules(camo_vendor_dir())
            CAMOImageDetector = sys.modules[
                "base_miner.deepfake_detectors.camo_detector"
            ].CAMOImageDetector
            vendor_detector = CAMOImageDetector(device="cpu")
            vendor_score = _as_score(vendor_detector(image))

        clear_camo_model_cache()
        ours = infer_camo_from_pil(image, device)

        assert ours == pytest.approx(vendor_score, abs=1e-8)
