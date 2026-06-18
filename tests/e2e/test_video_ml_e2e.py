"""E2E simulado VideoFACT — plugin + artefatos."""

from __future__ import annotations

from pathlib import Path

import pytest

WORKSPACE = Path(__file__).resolve().parents[2]


@pytest.mark.e2e
def test_technique_registered():
    from core.plugin_registry import PluginRegistry

    reg = PluginRegistry()
    plugins_dir = WORKSPACE / "src" / "backend" / "core" / "plugins"
    reg.discover_and_register(str(plugins_dir))
    names = set(reg.list_plugins())
    assert "videofact" in names
    assert "stil_video_detection" in names
    assert "lowres_fake_video" in names


@pytest.mark.e2e
def test_videofact_runtime_probe():
    from core.technique_runtime import technique_runtime_status

    ok, reason = technique_runtime_status("videofact")
    assert isinstance(ok, bool)
    assert isinstance(reason, str)
