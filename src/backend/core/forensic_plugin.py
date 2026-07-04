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
        """Return a JSON Schema describing accepted analysis parameters."""
        return None

    @abstractmethod
    def analyze(self, evidence_path: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Run the forensic analysis on the given evidence.

        Args:
            evidence_path: Path to the evidence file.
            parameters: Dictionary of analysis parameters.

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
