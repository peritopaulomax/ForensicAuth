"""E2E TruFor oficial — tampered1.png (GRIP-UNINA demo)."""

from __future__ import annotations

from pathlib import Path

import pytest

WORKSPACE = Path(__file__).resolve().parents[2]
TAMPERED1 = WORKSPACE / "uploads-dev" / "80fa2db4-3ca3-44d2-8c60-741190c3ec96.png"


@pytest.mark.integration
class TestTruForOfficialTampered1:
    def test_runtime_ready(self):
        from core.legacy.imdlbenco.trufor_official_pipeline import official_runtime_ready

        ok, reason = official_runtime_ready()
        if not ok:
            pytest.skip(reason)
        assert ok

    @pytest.mark.skipif(not TAMPERED1.is_file(), reason="tampered1.png ausente em uploads-dev")
    def test_pipeline_matches_official_score_band(self):
        from core.legacy.imdlbenco.trufor_official_pipeline import run_trufor_official_analysis

        result = run_trufor_official_analysis(str(TAMPERED1), threshold=0.5)
        assert result.original_size == (1536, 2048)
        assert result.integrity_score is not None
        assert result.integrity_score >= 0.95
        assert result.confidence_image is not None

    @pytest.mark.skipif(not TAMPERED1.is_file(), reason="tampered1.png ausente em uploads-dev")
    def test_localization_highlights_left_forgery_region(self):
        import numpy as np

        from core.legacy.imdlbenco.trufor_official_pipeline import _infer_official

        try:
            import torch
        except ImportError:
            pytest.skip("torch ausente")

        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        payload = _infer_official(str(TAMPERED1), device)
        loc = payload["map"]
        h, w = loc.shape
        left = float(loc[:, : w // 3].mean())
        center = float(loc[:, w // 3 : 2 * w // 3].mean())
        assert left > center * 5.0
        assert left > 0.2

    @pytest.mark.skipif(not TAMPERED1.is_file(), reason="tampered1.png ausente em uploads-dev")
    def test_trufor_gpu_cache_survives_second_run(self):
        import torch
        from core.legacy.imdlbenco.trufor_official_pipeline import _infer_official, _load_model

        img = str(TAMPERED1)
        if not TAMPERED1.is_file():
            pytest.skip("tampered1.png ausente")
        if not torch.cuda.is_available():
            pytest.skip("CUDA indisponivel")

        _infer_official(img, torch.device("cuda"))
        model = _load_model(torch.device("cuda"))
        assert next(model.parameters()).device.type == "cuda"
        _infer_official(img, torch.device("cuda"))

    def test_imdlbenco_adapter_trufor_path(self):
        from core.legacy.imdlbenco.imdlbenco_pipeline import run_imdlbenco_analysis
        from core.legacy.imdlbenco.trufor_official_pipeline import official_runtime_ready

        ok, reason = official_runtime_ready()
        if not ok:
            pytest.skip(reason)

        result = run_imdlbenco_analysis(str(TAMPERED1), method="trufor", threshold=0.5)
        assert result.method_id == "trufor"
        assert result.integrity_score is not None
        assert result.integrity_score >= 0.95
        assert result.confidence_image is not None
        assert result.inference_window_note is None
