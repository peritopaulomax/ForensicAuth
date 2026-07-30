"""Abstract base class for forensic analysis plugins."""

from abc import ABC, abstractmethod
from typing import Any, Dict, Tuple


class ForensicPlugin(ABC):
    """Abstract base class that all forensic analysis plugins must implement."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the plugin's unique name."""
        ...

    @property
    @abstractmethod
    def supported_types(self) -> list[str]:
        """Return list of evidence types this plugin can analyze."""
        ...

    @property
    def description(self) -> str | None:
        """Return a short human-readable description of the technique."""
        return None

    @property
    def parameters_schema(self) -> dict[str, Any] | None:
        """Return a JSON Schema describing accepted analysis parameters.

        Use extensions (``x-forensic-*``) to declare evidence roles:
            - ``x-forensic-role``: "questioned", "reference", "fingerprint", etc.
            - ``x-forensic-media``: "imagem", "audio", "video", "pdf".
            - ``x-forensic-multiple``: true for list-valued evidence IDs.
        """
        return None

    @property
    def result_schema(self) -> dict[str, Any] | None:
        """Declare expected artifacts and their roles.

        Example::
            {
                "artifacts": [
                    {"key": "heatmap_path", "filename": "heatmap.png", "role": "heatmap"},
                    {"key": "overlay_path", "filename": "overlay.png", "role": "overlay"},
                ]
            }
        """
        return None

    @property
    def runtime_manifest(self) -> dict[str, Any] | None:
        """Return runtime requirements (e.g., models, libraries)."""
        return None

    @property
    def reproducibility_manifest(self) -> dict[str, Any] | None:
        """Return reproducibility metadata: primary artifact and determinism profile."""
        return None

    @property
    def provenance_contract(self) -> dict[str, Any] | None:
        """Return provenance contract: parent_roles, min_parameters, savable_artifacts."""
        return None

    def is_runtime_available(self) -> Tuple[bool, str | None]:
        """Check whether the technique can run in this environment.

        Returns:
            Tuple of (available, reason). Reason is None when available.
        """
        return True, None

    @abstractmethod
    def analyze(self, evidence_path: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Run the forensic analysis on the given evidence.

        Args:
            evidence_path: Path to the evidence file.
            parameters: Dictionary of analysis parameters (with evidence IDs already
                resolved to paths/labels by the orchestration layer).

        Returns:
            Dictionary with analysis results.
        """
        ...

    @abstractmethod
    def validate_parameters(self, parameters: Dict[str, Any]) -> Tuple[bool, str]:
        """Validate the provided parameters for this plugin.

        Args:
            parameters: Dictionary of parameters to validate.

        Returns:
            Tuple of (is_valid, error_message).
        """
        ...
