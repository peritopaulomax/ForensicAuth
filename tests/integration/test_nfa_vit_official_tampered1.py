"""E2E NFA-ViT (BR-Gen) — localizacao de manipulacao."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

WORKSPACE = Path(__file__).resolve().parents[2]
TAMPERED1 = WORKSPACE / "uploads-dev" / "80fa2db4-3ca3-44d2-8c60-741190c3ec96.png"
AUTHENTIC = WORKSPACE / "uploads-dev" / "7bab0877-d873-4b68-aad9-de2e79ca14e7.jpg"


def _left_center_stats(heatmap: np.ndarray) -> tuple[float, float, float]:
    h, w = heatmap.shape
    left = float(heatmap[:, : w // 3].mean())
    center = float(heatmap[:, w // 3 : 2 * w // 3].mean())
    p95 = float(np.percentile(heatmap, 95))
    return left, center, p95


@pytest.mark.integration
class TestNfaVitOfficial:
    def test_runtime_ready(self):
        from core.legacy.imdlbenco.nfa_vit_official_pipeline import official_runtime_ready

        ok, reason = official_runtime_ready()
        if not ok:
            pytest.skip(reason)
        assert ok

    @pytest.mark.skipif(not TAMPERED1.is_file(), reason="tampered1.png ausente em uploads-dev")
    def test_localization_on_tampered1(self):
        from core.legacy.imdlbenco.nfa_vit_official_pipeline import (
            official_runtime_ready,
            run_nfa_vit_official_analysis,
        )

        ok, reason = official_runtime_ready()
        if not ok:
            pytest.skip(reason)

        result = run_nfa_vit_official_analysis(str(TAMPERED1), threshold=0.5)
        assert result.original_size == (1536, 2048)

        hm = np.array(result.heatmap_image.convert("L"), dtype=np.float32) / 255.0
        left, center, p95 = _left_center_stats(hm)
        assert left > center * 2.0, f"Regiao esquerda fraca (left={left:.4f}, center={center:.4f})"
        assert p95 >= 0.05, f"P95 baixo (p95={p95:.3f})"

    @pytest.mark.skipif(not AUTHENTIC.is_file(), reason="example_input.jpg ausente")
    def test_authentic_mostly_low(self):
        from core.legacy.imdlbenco.nfa_vit_official_pipeline import (
            official_runtime_ready,
            run_nfa_vit_official_analysis,
        )

        ok, reason = official_runtime_ready()
        if not ok:
            pytest.skip(reason)

        result = run_nfa_vit_official_analysis(str(AUTHENTIC), threshold=0.5)
        hm = np.array(result.heatmap_image.convert("L"), dtype=np.float32) / 255.0
        assert result.mean_score < 0.15, f"Autentica com score alto ({result.mean_score:.4f})"
        assert float((hm > 0.5).mean()) < 0.15

    def test_pipeline_routes_nfa_vit(self):
        from core.legacy.imdlbenco.imdlbenco_pipeline import run_imdlbenco_analysis
        from core.legacy.imdlbenco.imdlbenco_runtime import method_runtime_status

        status, reason = method_runtime_status("nfa_vit")
        if status != "ready":
            pytest.skip(reason or "NFA-ViT indisponivel")

        if not TAMPERED1.is_file():
            pytest.skip("tampered1.png ausente")

        out = run_imdlbenco_analysis(str(TAMPERED1), method="nfa_vit", threshold=0.5)
        assert out.method_id == "nfa_vit"
        assert out.heatmap_image is not None
