"""Unit tests for DeeCLIP runtime wiring."""

from __future__ import annotations


class TestDeeclipRuntime:
    def test_runtime_status_reports_missing_assets_or_ok(self):
        from core.legacy.deeclip.deeclip_runtime import deeclip_runtime_status

        ok, reason = deeclip_runtime_status()
        if ok:
            assert reason == ""
        else:
            assert "DeeCLIP" in reason or "CLIP" in reason or "Dependencias" in reason

    def test_vendor_class_is_loadable_when_assets_present(self):
        from core.legacy.deeclip.deeclip_runtime import deeclip_runtime_status
        from core.legacy.deeclip.deeclip_vendor import load_deeclip_class

        ok, reason = deeclip_runtime_status()
        if not ok:
            assert reason
            return

        cls = load_deeclip_class()
        assert cls.__name__ == "DeeCLIP"

    def test_deeclip_does_not_poison_global_hf_cache(self, monkeypatch):
        from core.legacy.deeclip.deeclip_pipeline import _load_processor, clear_deeclip_model_cache
        from core.legacy.deeclip.deeclip_runtime import deeclip_runtime_status

        ok, reason = deeclip_runtime_status()
        if not ok:
            assert reason
            return

        monkeypatch.setenv("HF_HUB_CACHE", "/tmp/forensicauth-original-hf-cache")
        _load_processor()
        assert __import__("os").environ["HF_HUB_CACHE"] == "/tmp/forensicauth-original-hf-cache"
        clear_deeclip_model_cache()
