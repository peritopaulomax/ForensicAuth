"""PluginRegistry must survive a broken adapter file during discovery."""

from __future__ import annotations

from pathlib import Path


def test_discover_skips_broken_plugin_file(tmp_path):
    from core.plugin_registry import PluginRegistry

    adapters = tmp_path / "plugins"
    adapters.mkdir()

    (adapters / "good_plugin.py").write_text(
        """
from core.forensic_plugin import ForensicPlugin

class GoodPlugin(ForensicPlugin):
    @property
    def name(self):
        return "good_technique"
    @property
    def supported_types(self):
        return ["imagem"]
    def analyze(self, evidence_path, parameters):
        return {"success": True}
    def validate_parameters(self, parameters):
        return True, ""
""",
        encoding="utf-8",
    )

    # SyntaxError on purpose (multiline string like the old scaffold bug)
    (adapters / "broken_plugin.py").write_text(
        '''
from core.forensic_plugin import ForensicPlugin

class BrokenPlugin(ForensicPlugin):
    @property
    def name(self):
        return "broken"
    @property
    def description(self):
        return "line1
line2"
    @property
    def supported_types(self):
        return ["imagem"]
    def analyze(self, evidence_path, parameters):
        return {"success": True}
    def validate_parameters(self, parameters):
        return True, ""
''',
        encoding="utf-8",
    )

    registry = PluginRegistry()
    registry.discover_and_register(str(adapters))
    assert "good_technique" in registry.list_plugins()
    assert "broken" not in registry.list_plugins()
