"""Unit tests for VRAM management before IAPL inference."""

from __future__ import annotations

from unittest.mock import MagicMock


class TestPrepareVramForIapl:
    def test_prepare_vram_calls_all_clear_caches(self, monkeypatch):
        calls: list[str] = []

        monkeypatch.setattr(
            "core.legacy.effort.effort_pipeline.clear_effort_model_cache",
            lambda: calls.append("effort"),
        )
        monkeypatch.setattr(
            "core.legacy.safe.safe_pipeline.clear_safe_model_cache",
            lambda: calls.append("safe"),
        )
        monkeypatch.setattr(
            "core.legacy.iapl.iapl_pipeline.clear_iapl_model_cache",
            lambda: calls.append("iapl"),
        )
        monkeypatch.setattr(
            "core.legacy.camo.camo_pipeline.clear_camo_model_cache",
            lambda: calls.append("camo"),
        )
        monkeypatch.setattr(
            "core.legacy.synthetic_image_detection.pipeline.release_gpu_memory",
            lambda: calls.append("synthetic"),
        )
        monkeypatch.setattr(
            "core.gpu_inference.cuda_memory_snapshot",
            lambda: {"free_mb": 1000, "total_mb": 10240, "allocated_mb": 500},
        )
        monkeypatch.setattr("core.gpu_inference.release_gpu_memory", MagicMock())

        from core.gpu_inference import prepare_vram_for_iapl

        result = prepare_vram_for_iapl(log=False)

        assert set(calls) == {"effort", "safe", "iapl", "camo", "synthetic"}
        assert calls.count("synthetic") >= 1
        assert "before" in result and "after" in result


class TestCapImageForResidue:
    def test_small_image_unchanged(self):
        from core.legacy.synthetic_image_detection.pipeline import _cap_image_for_residue
        from PIL import Image

        img = Image.new("RGB", (800, 600))
        assert _cap_image_for_residue(img).size == (800, 600)

    def test_large_image_scaled_down(self):
        from core.legacy.synthetic_image_detection.pipeline import _cap_image_for_residue
        from PIL import Image

        img = Image.new("RGB", (4000, 3000))
        out = _cap_image_for_residue(img, max_side=2048)
        assert max(out.size) == 2048
