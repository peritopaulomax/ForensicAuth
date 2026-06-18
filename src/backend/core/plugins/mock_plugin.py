"""Mock plugin for testing the job system."""

from typing import Any, Dict, Tuple

from core.forensic_plugin import ForensicPlugin


class MockPlugin(ForensicPlugin):
    """A mock forensic plugin that always succeeds for testing."""

    @property
    def name(self) -> str:
        return "mock_technique"

    @property
    def supported_types(self) -> list[str]:
        return ["imagem", "audio", "video", "pdf"]

    def analyze(self, evidence_path: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "success": True,
            "metrics": {"score": 0.99},
            "artifacts": [],
        }

    def validate_parameters(self, parameters: Dict[str, Any]) -> Tuple[bool, str]:
        if "invalid_param" in parameters:
            return False, "Parametro 'invalid_param' nao reconhecido"
        return True, ""
