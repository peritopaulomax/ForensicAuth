"""Unit tests for CLIDE runtime wiring."""

from __future__ import annotations


class TestClideRuntime:
    def test_runtime_status_reports_missing_assets_or_ok(self):
        from core.legacy.clide.clide_runtime import clide_runtime_status

        ok, reason = clide_runtime_status()
        if ok:
            assert reason == ""
        else:
            assert "CLIDE" in reason or "CLIP" in reason or "Dependencias" in reason

    def test_vendor_detection_module_loads_when_present(self):
        from core.legacy.clide.clide_runtime import clide_vendor_dir
        from core.legacy.clide.clide_vendor import load_detection_module

        if not (clide_vendor_dir() / "detection.py").is_file():
            return
        module = load_detection_module()
        assert hasattr(module, "likelihood_from_mat")
        assert hasattr(module, "sphx")
