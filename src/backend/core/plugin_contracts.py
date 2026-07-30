"""Declarative contracts bridge between ForensicPlugin and central registries.

Plugins devem declarar ``reproducibility_manifest`` e ``provenance_contract``.
Tecnicas ainda sem declaracao usam os registries centrais
(``REPRODUCIBILITY_REGISTRY`` e ``TECHNIQUE_PROVENANCE_CONTRACT``) como fallback.
"""

from __future__ import annotations

from typing import Any

from core.plugin_registry import get_plugin_registry
from core.reproducibility import REPRODUCIBILITY_REGISTRY
from services.derivation_contract import TECHNIQUE_PROVENANCE_CONTRACT


def _plugin_instance(technique: str) -> Any | None:
    registry = get_plugin_registry()
    plugin_cls = registry.PLUGINS.get(technique)
    if plugin_cls is None:
        return None
    return plugin_cls()


def reproducibility_manifest(technique: str) -> dict[str, Any]:
    """Return reproducibility manifest for a technique.

    Prefers the plugin's own declaration, falls back to the central registry.
    """
    plugin = _plugin_instance(technique)
    if plugin is not None:
        manifest = plugin.reproducibility_manifest
        if manifest:
            return dict(manifest)
    return dict(REPRODUCIBILITY_REGISTRY.get(technique) or {})


def provenance_contract(technique: str) -> dict[str, Any] | None:
    """Return provenance contract for a technique.

    Prefers the plugin's own declaration, falls back to the central registry.
    """
    plugin = _plugin_instance(technique)
    if plugin is not None:
        contract = plugin.provenance_contract
        if contract:
            return dict(contract)
    return TECHNIQUE_PROVENANCE_CONTRACT.get(technique)


def runtime_manifest(technique: str) -> dict[str, Any] | None:
    """Return runtime requirements declared by a plugin, if any."""
    plugin = _plugin_instance(technique)
    if plugin is None:
        return None
    manifest = plugin.runtime_manifest
    return dict(manifest) if manifest else None


def result_schema(technique: str) -> dict[str, Any] | None:
    """Return result schema declared by a plugin, if any."""
    plugin = _plugin_instance(technique)
    if plugin is None:
        return None
    schema = plugin.result_schema
    return dict(schema) if schema else None
