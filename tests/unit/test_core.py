"""Tests for core module — TDD Red phase.

Expected: ALL tests fail because PluginRegistry, ForensicPlugin, etc. do not exist yet.
"""

import os
import sys

import pytest


class TestPluginRegistry:
    """TU-CORE-001 to TU-CORE-004"""

    def test_discover_and_register_plugins(self, tmp_path):
        """TU-CORE-001: Registry discovers valid plugins and ignores invalid ones."""
        from core.plugin_registry import PluginRegistry
        registry = PluginRegistry()
        # Create a temp directory with mock plugins
        adapters_dir = tmp_path / "adapters"
        adapters_dir.mkdir()

        # Write a mock plugin file
        plugin_file = adapters_dir / "mock_plugin.py"
        plugin_file.write_text("""
from core.forensic_plugin import ForensicPlugin
from typing import Any, Dict

class MockPlugin(ForensicPlugin):
    @property
    def name(self): return "mock_test"
    @property
    def supported_types(self): return ["imagem"]
    def analyze(self, evidence_path, parameters): return {"success": True}
    def validate_parameters(self, parameters): return True, ""
""")

        registry.discover_and_register(str(adapters_dir))

        assert "mock_test" in registry.PLUGINS
        assert len(registry.PLUGINS) >= 1

    def test_abstract_plugin_not_instantiable(self):
        """TU-CORE-002: ForensicPlugin cannot be instantiated directly."""
        from core.forensic_plugin import ForensicPlugin
        with pytest.raises(TypeError):
            ForensicPlugin()

    def test_valid_plugin_implementation(self):
        """TU-CORE-003: Valid plugin inherits ForensicPlugin and works."""
        from core.forensic_plugin import ForensicPlugin

        class ValidPlugin(ForensicPlugin):
            @property
            def name(self): return "valid"
            @property
            def supported_types(self): return ["imagem"]
            def analyze(self, evidence_path, parameters): return {"success": True}
            def validate_parameters(self, parameters): return True, ""

        plugin = ValidPlugin()
        assert plugin.name == "valid"
        assert plugin.validate_parameters({}) == (True, "")

    def test_plugin_parameter_validation(self):
        """TU-CORE-004: Plugin validates parameters correctly."""
        from core.forensic_plugin import ForensicPlugin

        class ValidPlugin(ForensicPlugin):
            @property
            def name(self): return "valid"
            @property
            def supported_types(self): return ["imagem"]
            def analyze(self, evidence_path, parameters): return {"success": True}
            def validate_parameters(self, parameters):
                if "invalid" in parameters:
                    return False, "Parametro 'invalid' nao reconhecido"
                return True, ""

        plugin = ValidPlugin()
        assert plugin.validate_parameters({}) == (True, "")
        assert plugin.validate_parameters({"invalid": 123}) == (False, "Parametro 'invalid' nao reconhecido")


class TestSettings:
    """TU-CORE-005 to TU-CORE-006"""

    def test_settings_load_from_env(self, monkeypatch):
        """TU-CORE-005: Settings load from environment variables."""
        from app.config import Settings
        monkeypatch.setenv("DATABASE_URL", "postgresql://test@localhost/db")
        monkeypatch.setenv("SECRET_KEY", "test123")

        settings = Settings()
        assert settings.DATABASE_URL == "postgresql://test@localhost/db"
        assert settings.SECRET_KEY == "test123"
        assert settings.ACCESS_TOKEN_EXPIRE_MINUTES == 30

    def test_settings_missing_required_fails(self, monkeypatch):
        """TU-CORE-006: Missing required env var raises ValidationError."""
        from app.config import Settings, get_settings
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.setenv("SECRET_KEY", "test")

        # Force re-evaluation by clearing lru_cache if present
        get_settings.cache_clear()

        with pytest.raises(Exception) as exc_info:
            Settings(_env_file=None)  # Isolate from .env file; Pydantic will raise ValidationError

        assert "DATABASE_URL" in str(exc_info.value)
