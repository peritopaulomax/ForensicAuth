"""Mock forensic plugins for testing."""

from typing import Any, Dict

from core.forensic_plugin import ForensicPlugin


class MockPluginA(ForensicPlugin):
    @property
    def name(self) -> str:
        return "mock_a"

    @property
    def supported_types(self) -> list[str]:
        return ["imagem"]

    def analyze(self, evidence_path: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "success": True,
            "artifacts": [],
            "metrics": {"score": 0.99},
            "logs": ["MockPluginA executed"],
        }

    def validate_parameters(self, parameters: Dict[str, Any]) -> tuple[bool, str]:
        return True, ""


class MockPluginB(ForensicPlugin):
    @property
    def name(self) -> str:
        return "mock_b"

    @property
    def supported_types(self) -> list[str]:
        return ["audio"]

    def analyze(self, evidence_path: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "success": True,
            "artifacts": [],
            "metrics": {"duration": 120},
            "logs": ["MockPluginB executed"],
        }

    def validate_parameters(self, parameters: Dict[str, Any]) -> tuple[bool, str]:
        return True, ""


class MockPluginC(ForensicPlugin):
    @property
    def name(self) -> str:
        return "mock_c"

    @property
    def supported_types(self) -> list[str]:
        return ["video", "pdf"]

    def analyze(self, evidence_path: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "success": True,
            "artifacts": [],
            "metrics": {"frames": 1000},
            "logs": ["MockPluginC executed"],
        }

    def validate_parameters(self, parameters: Dict[str, Any]) -> tuple[bool, str]:
        if "invalid" in parameters:
            return False, f"Parametro 'invalid' nao reconhecido"
        return True, ""


class MockInvalidPlugin:
    """Does NOT inherit from ForensicPlugin — should be ignored by registry."""
    pass
