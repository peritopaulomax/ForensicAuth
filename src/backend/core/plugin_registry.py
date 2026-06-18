"""Plugin registry for discovering and registering forensic analysis plugins."""

import importlib.util
import os
from pathlib import Path
from typing import Dict, Type

from core.forensic_plugin import ForensicPlugin

# Tecnicas mantidas no codigo mas sem registro ativo (card/UI pendente).
STANDBY_PLUGIN_NAMES = frozenset({
    "deepfake_similarity",
    "mp3_parser",
    "opus_parser",
    "wav_ima_adpcm",
    "pdf_touchup",
})


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

            self._load_and_register(file_path)

    def _load_and_register(self, file_path: Path) -> None:
        """Load a single Python file and register valid plugin classes."""
        spec = importlib.util.spec_from_file_location(file_path.stem, file_path)
        if spec is None or spec.loader is None:
            return

        module = importlib.util.module_from_spec(spec)
        # Ensure core.forensic_plugin is available in the module's namespace
        # by injecting it into sys.modules if needed
        import sys
        sys.modules.setdefault("core.forensic_plugin", __import__("core.forensic_plugin", fromlist=["ForensicPlugin"]))

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
