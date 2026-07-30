"""Plugin registry for discovering and registering forensic analysis plugins."""

from __future__ import annotations

import importlib.util
import logging
import sys
from pathlib import Path
from typing import Dict, Optional, Type

from core.forensic_plugin import ForensicPlugin

logger = logging.getLogger(__name__)

# Nomes descobertos mas nao registrados (reserva vazia — sem standby ativo).
STANDBY_PLUGIN_NAMES: frozenset[str] = frozenset()

_GLOBAL_REGISTRY: Optional["PluginRegistry"] = None


def default_plugins_dir() -> Path:
    return Path(__file__).resolve().parent / "plugins"


def get_plugin_registry(*, rediscover: bool = False) -> "PluginRegistry":
    """Singleton com discovery dos plugins em ``core/plugins``."""
    global _GLOBAL_REGISTRY
    if _GLOBAL_REGISTRY is None or rediscover:
        registry = PluginRegistry()
        registry.discover_and_register(str(default_plugins_dir()))
        _GLOBAL_REGISTRY = registry
    return _GLOBAL_REGISTRY


class PluginRegistry:
    """Registry that discovers and holds references to forensic plugins."""

    def __init__(self):
        self.PLUGINS: Dict[str, Type[ForensicPlugin]] = {}

    def discover_and_register(self, adapters_dir: str) -> None:
        """Discover plugin classes in the given directory and register them.

        Scans all *.py files in ``adapters_dir``, imports them, and registers
        any class that inherits from :class:`ForensicPlugin` (excluding the
        base class itself).
        """
        adapters_path = Path(adapters_dir)
        if not adapters_path.exists():
            return

        for file_path in adapters_path.glob("*.py"):
            if file_path.name.startswith("_"):
                continue
            try:
                self._load_and_register(file_path)
            except Exception as exc:
                # Um plugin quebrado nao deve derrubar /analysis/techniques.
                logger.warning(
                    "Falha ao carregar plugin %s: %s",
                    file_path.name,
                    exc,
                    exc_info=True,
                )

    def _load_and_register(self, file_path: Path) -> None:
        """Load a single Python file and register valid plugin classes."""
        spec = importlib.util.spec_from_file_location(file_path.stem, file_path)
        if spec is None or spec.loader is None:
            return

        module = importlib.util.module_from_spec(spec)
        sys.modules.setdefault(
            "core.forensic_plugin",
            __import__("core.forensic_plugin", fromlist=["ForensicPlugin"]),
        )

        spec.loader.exec_module(module)

        for attr_name in dir(module):
            obj = getattr(module, attr_name)
            if (
                isinstance(obj, type)
                and issubclass(obj, ForensicPlugin)
                and obj is not ForensicPlugin
            ):
                try:
                    instance = obj()
                    if instance.name in STANDBY_PLUGIN_NAMES:
                        continue
                    self.PLUGINS[instance.name] = obj
                except Exception:
                    # If instantiation fails (e.g., abstract methods not implemented),
                    # skip this class
                    pass

    def get(self, name: str) -> Type[ForensicPlugin]:
        """Retrieve a registered plugin class by name."""
        return self.PLUGINS[name]

    def list_plugins(self) -> list[str]:
        """Return a list of registered plugin names."""
        return list(self.PLUGINS.keys())
