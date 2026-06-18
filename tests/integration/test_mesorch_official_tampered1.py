"""E2E Mesorch — tampered1.png + copy-move sintetico (forgery localization)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

WORKSPACE = Path(__file__).resolve().parents[2]
TAMPERED1 = WORKSPACE / "uploads-dev" / "80fa2db4-3ca3-44d2-8c60-741190c3ec96.png"
AUTHENTIC = WORKSPACE / "uploads-dev" / "7bab0877-d873-4b68-aad9-de2e79ca14e7.jpg"


def _left_center_stats(heatmap: np.ndarray) -> tuple[float, float, float]:
    h, w = heatmap.shape
    left = float(heatmap[:, : w // 3].mean())
    center = float(heatmap[:, w // 3 : 2 * w // 3].mean())
    p95 = float(np.percentile(heatmap, 95))
    return left, center, p95


def _make_copymove_fixture(src: Path) -> Path:
    base = np.array(Image.open(src).convert("RGB"))
    patch = base[500:700, 80:280].copy()
    y0, x0 = 120, 700
    base[y0 : y0 + 200, x0 : x0 + 200] = patch
    tmp = Path(tempfile.mkdtemp()) / "mesorch_copymove.jpg"
    Image.fromarray(base).save(tmp, quality=95)
    return tmp


@pytest.mark.integration
class TestMesorchOfficialTampered1:
    def test_runtime_ready(self):
        from core.legacy.imdlbenco.mesorch_official_pipeline import official_runtime_ready

        ok, reason = official_runtime_ready()
        if not ok:
            pytest.skip(reason)
        assert ok

    @pytest.mark.skipif(not TAMPERED1.is_file(), reason="tampered1.png ausente em uploads-dev")
    def test_localization_highlights_left_forgery_region(self):
        from core.legacy.imdlbenco.mesorch_official_pipeline import run_mesorch_official_analysis

        result = run_mesorch_official_analysis(str(TAMPERED1), threshold=0.5)
        assert result.original_size == (1536, 2048)

        hm = np.array(result.heatmap_image.convert("L"), dtype=np.float32) / 255.0
        left, center, p95 = _left_center_stats(hm)

        assert left > center * 10.0, f"Regiao esquerda fraca (left={left:.4f}, center={center:.4f})"
        assert left > 0.05, f"Ativacao esquerda baixa (left={left:.4f})"
        assert p95 >= 0.10, f"P95 baixo para imagem forjada (p95={p95:.3f})"

    @pytest.mark.skipif(not AUTHENTIC.is_file(), reason="example_input.jpg ausente em uploads-dev")
    def test_authentic_image_stays_mostly_low(self):
        from core.legacy.imdlbenco.mesorch_official_pipeline import run_mesorch_official_analysis

        result = run_mesorch_official_analysis(str(AUTHENTIC), threshold=0.5)
        hm = np.array(result.heatmap_image.convert("L"), dtype=np.float32) / 255.0

        assert result.mean_score < 0.08, f"Imagem autentica com score alto ({result.mean_score:.4f})"
        assert float((hm > 0.5).mean()) < 0.08, "Muitos pixels forjados em imagem autentica"

    @pytest.mark.skipif(not AUTHENTIC.is_file(), reason="example_input.jpg ausente em uploads-dev")
    def test_copymove_produces_clean_high_mask(self):
        from core.legacy.imdlbenco.mesorch_official_pipeline import run_mesorch_official_analysis

        forged_path = _make_copymove_fixture(AUTHENTIC)
        result = run_mesorch_official_analysis(str(forged_path), threshold=0.5)
        hm = np.array(result.heatmap_image.convert("L"), dtype=np.float32) / 255.0

        y0, x0 = 120, 700
        forged = hm[y0 : y0 + 200, x0 : x0 + 200]
        assert float(forged.mean()) >= 0.70, f"Mascara copy-move fraca (mean={forged.mean():.3f})"
        assert float((forged > 0.5).mean()) >= 0.60, "Poucos pixels na regiao forjada"

    @pytest.mark.skipif(not TAMPERED1.is_file(), reason="tampered1.png ausente em uploads-dev")
    def test_imdlbenco_adapter_routes_to_official(self):
        from core.legacy.imdlbenco.imdlbenco_pipeline import run_imdlbenco_analysis
        from core.legacy.imdlbenco.mesorch_official_pipeline import official_runtime_ready

        ok, reason = official_runtime_ready()
        if not ok:
            pytest.skip(reason)

        result = run_imdlbenco_analysis(str(TAMPERED1), method="mesorch", threshold=0.5)
        assert result.method_id == "mesorch"
        hm = np.array(result.heatmap_image.convert("L"), dtype=np.float32) / 255.0
        left, center, _ = _left_center_stats(hm)
        assert left > center * 10.0

    @pytest.mark.skipif(not TAMPERED1.is_file(), reason="tampered1.png ausente em uploads-dev")
    def test_mesorch_p_variant_loads(self):
        from core.legacy.imdlbenco.mesorch_official_pipeline import (
            official_runtime_ready,
            run_mesorch_official_analysis,
        )

        ok, reason = official_runtime_ready(mesorch_variant="mesorch_p")
        if not ok:
            pytest.skip(reason)

        result = run_mesorch_official_analysis(
            str(TAMPERED1),
            threshold=0.5,
            mesorch_variant="mesorch_p",
        )
        assert result.mesorch_variant == "mesorch_p"
        hm = np.array(result.heatmap_image.convert("L"), dtype=np.float32) / 255.0
        left, center, _ = _left_center_stats(hm)
        assert left > center * 5.0
