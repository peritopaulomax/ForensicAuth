"""Tests for GPU VRAM residency policy."""

from __future__ import annotations

from unittest.mock import patch


class TestGpuResidency:
    def test_should_keep_synthetic_when_flag_true(self, monkeypatch):
        monkeypatch.setenv("SYNTHETIC_KEEP_RESIDENT", "true")
        monkeypatch.setenv("GPU_RESIDENT_TECHNIQUES", "synthetic,effort,safe")

        from app.config import get_settings

        get_settings.cache_clear()
        from core.gpu_residency import should_keep_resident

        assert should_keep_resident("synthetic_image_detection") is True
        get_settings.cache_clear()

    def test_prepare_iapl_skips_when_vram_ok(self, monkeypatch):
        monkeypatch.setenv("GPU_MIN_FREE_MB", "1500")
        monkeypatch.setenv("GPU_RESERVED_FUTURE_MB", "7000")

        from app.config import get_settings

        get_settings.cache_clear()

        snap = {"free_mb": 20000, "total_mb": 24000, "allocated_mb": 1000}
        with patch("core.gpu_residency.cuda_memory_snapshot", return_value=snap, create=True):
            with patch("core.gpu_residency.vram_under_pressure", return_value=False):
                from core.gpu_residency import prepare_vram_for_iapl_if_needed

                out = prepare_vram_for_iapl_if_needed()
                assert out.get("skipped") is True

        get_settings.cache_clear()

    def test_maybe_evict_skips_when_resident_and_ok(self, monkeypatch):
        monkeypatch.setenv("SYNTHETIC_KEEP_RESIDENT", "true")

        from app.config import get_settings

        get_settings.cache_clear()

        with patch("core.gpu_residency.vram_under_pressure", return_value=False):
            with patch("core.gpu_inference.purge_foreign_gpu_model_caches") as purge:
                from core.gpu_residency import maybe_evict_for_job

                maybe_evict_for_job("synthetic_image_detection")
                purge.assert_not_called()

        get_settings.cache_clear()
