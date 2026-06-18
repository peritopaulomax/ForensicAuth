"""E2E simulado: CAMO no pipeline completo de detecção de imagens sinteticas."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PIL import Image

WORKSPACE = Path(__file__).resolve().parents[2]
FIXTURE = WORKSPACE / "uploads-dev" / "7bab0877-d873-4b68-aad9-de2e79ca14e7.jpg"


@pytest.mark.e2e
class TestCamoSyntheticE2E:
    def test_full_analysis_includes_camo_row_simulated(self, monkeypatch, tmp_path):
        """Simula ensemble completo com CAMO mockado (sem pesos reais)."""
        import torch

        from core.legacy.camo.camo_runtime import MODEL_LABEL
        from core.legacy.synthetic_image_detection import pipeline as sp

        monkeypatch.setattr(
            "core.legacy.camo.camo_pipeline.camo_runtime_status",
            lambda: (True, ""),
        )
        monkeypatch.setattr(
            "core.legacy.camo.camo_pipeline.run_with_device_fallback",
            lambda fn, **_: (fn(torch.device("cpu")), torch.device("cpu")),
        )
        monkeypatch.setattr(
            "core.legacy.camo.camo_pipeline.infer_camo_from_pil",
            lambda *_a, **_k: 0.55,
        )

        sp._DETECTION_MODELS = None
        sp._MODEL1_XGB = None
        sp._FFT_EXTRACTOR = None
        sp._LOAD_ERROR = None

        from core.legacy.synthetic_image_detection.runtime import runtime_status

        ok, reason = runtime_status()
        if not ok:
            pytest.skip(reason or "ensemble base indisponivel")

        img = (
            Image.open(FIXTURE).convert("RGB")
            if FIXTURE.is_file()
            else Image.new("RGB", (320, 240), (90, 110, 130))
        )

        rows = sp.predict_ensemble(img)
        camo_rows = [r for r in rows if r[0] == MODEL_LABEL]
        assert len(camo_rows) == 1
        assert camo_rows[0][1] == "0.5500"

    def test_adapter_analyze_writes_model_scores_with_camo(self, monkeypatch, tmp_path):
        """Simula job do adapter com CAMO mockado e artefato model_scores.txt."""
        from core.legacy.camo.camo_runtime import MODEL_LABEL
        from core.legacy.effort.effort_pipeline import effort_row
        from core.plugins.synthetic_image_detection_adapter import SyntheticImageDetectionAdapter

        monkeypatch.setattr(
            "core.plugins.synthetic_image_detection_adapter.runtime_status",
            lambda: (True, ""),
        )
        monkeypatch.setattr(
            "core.plugins.synthetic_image_detection_adapter.run_synthetic_image_detection_analysis",
            lambda image, **kwargs: {
                "individual_results": [
                    effort_row("ai-image-detector-deploy", 0.4, inference_device="cuda"),
                    effort_row(MODEL_LABEL, 0.71, inference_device="cpu"),
                ],
                "inference_device": "cuda",
                "input_image": image,
                "input_fft": None,
            },
        )

        evidence = tmp_path / "sample.jpg"
        Image.new("RGB", (256, 256), (120, 140, 160)).save(evidence)

        adapter = SyntheticImageDetectionAdapter()
        ok, msg = adapter.validate_parameters({"mode": "fast", "generate_visuals": False})
        assert ok, msg

        result = adapter.analyze(
            str(evidence),
            {
                "mode": "fast",
                "generate_visuals": False,
                "_job_staging_dir": str(tmp_path / "out"),
            },
        )
        assert result["success"] is True

        scores_path = Path(result["model_scores_txt_path"])
        text = scores_path.read_text(encoding="utf-8")
        assert MODEL_LABEL in text
        assert "0.7100" in text

    def test_health_exposes_camo_warmup(self):
        from core.legacy.camo.camo_warmup import camo_warmup_status

        status = camo_warmup_status()
        assert "status" in status
        assert "cache_keys" in status

    def test_prepare_vram_clears_camo_cache(self, monkeypatch):
        calls: list[str] = []

        monkeypatch.setattr(
            "core.legacy.camo.camo_pipeline.clear_camo_model_cache",
            lambda: calls.append("camo"),
        )
        monkeypatch.setattr(
            "core.legacy.effort.effort_pipeline.clear_effort_model_cache",
            lambda: calls.append("effort"),
        )
        monkeypatch.setattr(
            "core.legacy.safe.safe_pipeline.clear_safe_model_cache",
            lambda: calls.append("safe"),
        )
        monkeypatch.setattr(
            "core.legacy.iapl.iapl_pipeline.clear_iapl_model_cache",
            lambda: calls.append("iapl"),
        )
        monkeypatch.setattr(
            "core.legacy.synthetic_image_detection.pipeline.release_gpu_memory",
            lambda: calls.append("synthetic"),
        )
        monkeypatch.setattr(
            "core.gpu_inference.cuda_memory_snapshot",
            lambda: {"free_mb": 1000, "total_mb": 10240, "allocated_mb": 500},
        )
        monkeypatch.setattr("core.gpu_inference.release_gpu_memory", MagicMock())

        from core.gpu_inference import prepare_vram_for_iapl

        prepare_vram_for_iapl(log=False)
        assert "camo" in calls
