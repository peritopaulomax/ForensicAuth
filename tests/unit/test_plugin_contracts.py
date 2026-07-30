"""Contratos declarativos e ciclo add/remove de tecnica (Fase E)."""

from __future__ import annotations

from typing import Any, Dict, Tuple

from core.forensic_plugin import ForensicPlugin
from core.plugin_contracts import (
    provenance_contract,
    reproducibility_manifest,
    result_schema,
    runtime_manifest,
)
from core.plugin_registry import get_plugin_registry
from core.technique_runtime import technique_runtime_status


class _DummySanitPlugin(ForensicPlugin):
    @property
    def name(self) -> str:
        return "sanit_dummy_technique"

    @property
    def supported_types(self) -> list[str]:
        return ["imagem"]

    @property
    def result_schema(self) -> dict[str, Any] | None:
        return {"artifacts": [{"key": "report_path", "filename": "report.txt", "role": "report"}]}

    @property
    def runtime_manifest(self) -> dict[str, Any] | None:
        return {"requires": [], "gpu": False}

    @property
    def reproducibility_manifest(self) -> dict[str, Any] | None:
        return {"primary": "report.txt", "profile": "strict"}

    @property
    def provenance_contract(self) -> dict[str, Any] | None:
        return {"parent_roles": ["questioned"], "savable_artifacts": ["report_path"]}

    def is_runtime_available(self) -> Tuple[bool, str | None]:
        return True, None

    def validate_parameters(self, parameters: Dict[str, Any]) -> Tuple[bool, str]:
        return True, ""

    def analyze(self, evidence_path: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        return {"success": True, "adapter": self.name}


def test_zero_grid_declares_contracts():
    assert runtime_manifest("zero_grid") is not None
    assert result_schema("zero_grid") is not None
    assert reproducibility_manifest("zero_grid").get("primary") == "votes_colored.png"
    assert provenance_contract("zero_grid") is not None
    assert "questioned" in provenance_contract("zero_grid")["parent_roles"]


def test_zero_grid_runtime_via_plugin():
    technique_runtime_status.cache_clear()
    ok, reason = technique_runtime_status("zero_grid")
    assert ok, reason


def test_dummy_plugin_register_and_unregister():
    registry = get_plugin_registry()
    assert "sanit_dummy_technique" not in registry.PLUGINS

    registry.PLUGINS["sanit_dummy_technique"] = _DummySanitPlugin
    try:
        assert registry.get("sanit_dummy_technique") is _DummySanitPlugin
        assert "sanit_dummy_technique" in registry.list_plugins()
        assert reproducibility_manifest("sanit_dummy_technique")["primary"] == "report.txt"
        technique_runtime_status.cache_clear()
        available, reason = technique_runtime_status("sanit_dummy_technique")
        assert available is True
        assert not reason
    finally:
        registry.PLUGINS.pop("sanit_dummy_technique", None)
        technique_runtime_status.cache_clear()
        assert "sanit_dummy_technique" not in registry.PLUGINS
