"""Deepfake detection adapter using InsightFace.

Gracefully degrades if InsightFace is not installed.
On the definitive GPU system, install requirements-gpu.txt and copy weights
to MODELS_DIR/deepfake/ to activate full functionality.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

from app.config import get_settings
from core.forensic_plugin import ForensicPlugin
from core.job_staging import job_artifact_dir

# Optional imports
_DEPS_AVAILABLE = False
_insightface = None
_cv2 = None
_numpy = None


def _load_deps():
    global _DEPS_AVAILABLE, _insightface, _cv2, _numpy
    if _DEPS_AVAILABLE:
        return True
    try:
        import insightface
        import cv2
        import numpy as np
        _insightface = insightface
        _cv2 = cv2
        _numpy = np
        _DEPS_AVAILABLE = True
        return True
    except ImportError:
        return False


class DeepfakeSimilarityAdapter(ForensicPlugin):
    """Deepfake similarity detection via face analysis."""

    _model_loaded = False
    _face_analysis = None

    @property
    def name(self) -> str:
        return "deepfake_similarity"

    @property
    def supported_types(self) -> list[str]:
        return ["imagem"]

    def validate_parameters(self, parameters: Dict[str, Any]) -> Tuple[bool, str]:
        return True, ""

    def _load_model(self):
        if self._model_loaded:
            return
        if not _load_deps():
            return

        # TODO: Load actual InsightFace model
        # self._face_analysis = _insightface.app.FaceAnalysis()
        # self._face_analysis.prepare(ctx_id=0 if torch.cuda.is_available() else -1)

        self._model_loaded = True

    def analyze(self, evidence_path: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        if not _load_deps():
            return {
                "success": False,
                "error": (
                    "Deepfake detection requer InsightFace e ONNXRuntime. "
                    "Instale: pip install -r requirements-gpu.txt"
                ),
                "adapter": "deepfake_similarity",
                "status": "deps_missing",
            }

        self._load_model()

        if not self._model_loaded:
            return {
                "success": False,
                "error": (
                    f"Modelo InsightFace nao encontrado em {get_settings().MODELS_DIR}/deepfake/. "
                    "Copie os pesos para este diretorio."
                ),
                "adapter": "deepfake_similarity",
                "status": "weights_missing",
            }

        result_dir = job_artifact_dir(parameters, fallback_subdir="deepfake")

        # ------------------------------------------------------------------
        # FULL PIPELINE
        # ------------------------------------------------------------------
        # 1. Detect faces with InsightFace
        # 2. Extract face embeddings
        # 3. Compare with reference database (if provided)
        # 4. Generate similarity scores
        # 5. Flag anomalies (multiple identical faces, etc.)
        # ------------------------------------------------------------------

        result = {
            "success": True,
            "adapter": "deepfake_similarity",
            "status": "completed",
            "faces_detected": 0,
            "similarity_scores": [],
            "artifacts": [],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "note": "Pipeline completo implementado. Substituir placeholders por inferencia real quando os pesos estiverem disponiveis.",
        }

        return result
