"""Unit tests for SAFIRE forged-region localization."""

import pytest


class TestSafireRuntime:
    def test_repo_present(self):
        from core.legacy.safire.safire_runtime import safire_repo_dir

        assert safire_repo_dir().is_dir()

    def test_runtime_status(self):
        from core.legacy.safire.safire_runtime import safire_runtime_status

        ok, reason = safire_runtime_status()
        if ok:
            assert reason == ""
        else:
            assert reason

    def test_vendor_import_context_ignores_preloaded_networks(self, monkeypatch):
        import sys
        import types

        from core.legacy.safire.safire_pipeline import _safire_vendor_context

        fake_networks = types.ModuleType("networks")
        fake_networks.__path__ = []
        monkeypatch.setitem(sys.modules, "networks", fake_networks)

        with _safire_vendor_context():
            from networks.safire_model import AdaptorSAM

            assert AdaptorSAM.__name__ == "AdaptorSAM"

        assert sys.modules["networks"] is fake_networks

    def test_vendor_import_context_prefers_safire_networks_over_sys_path_collision(
        self, monkeypatch, tmp_path
    ):
        from core.legacy.safire.safire_pipeline import _safire_vendor_context

        competing_vendor = tmp_path / "competing_vendor"
        competing_networks = competing_vendor / "networks"
        competing_networks.mkdir(parents=True)
        (competing_networks / "__init__.py").write_text("", encoding="utf-8")
        monkeypatch.syspath_prepend(str(competing_vendor))

        with _safire_vendor_context():
            from networks.safire_model import AdaptorSAM

            assert AdaptorSAM.__name__ == "AdaptorSAM"

    def test_plugin_registered(self):
        from pathlib import Path

        from core.plugin_registry import PluginRegistry

        plugins_dir = Path(__file__).resolve().parents[2] / "src" / "backend" / "core" / "plugins"
        registry = PluginRegistry()
        registry.discover_and_register(str(plugins_dir))
        assert registry.get("safire") is not None

    def test_validate_parameters_mode(self):
        from unittest.mock import patch

        from core.plugins.safire_adapter import SafireAdapter

        with patch("core.plugins.safire_adapter.safire_runtime_status", return_value=(True, "")):
            adapter = SafireAdapter()
            ok, msg = adapter.validate_parameters({"mode": "invalid"})
            assert not ok
            assert "mode" in msg.lower()


class TestSafireAdapter:
    def test_supported_types(self):
        from core.plugins.safire_adapter import SafireAdapter

        assert SafireAdapter().supported_types == ["imagem"]
