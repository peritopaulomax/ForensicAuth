"""E2E CAT-Net — example_input.jpg (README oficial mjkwon2021/CAT-Net)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

WORKSPACE = Path(__file__).resolve().parents[2]
EXAMPLE = WORKSPACE / "uploads-dev" / "7bab0877-d873-4b68-aad9-de2e79ca14e7.jpg"


def _zone_stats(heatmap: np.ndarray) -> dict[str, float]:
    h, w = heatmap.shape
    tree = heatmap[:, : int(w * 0.42)]
    sign = heatmap[:, int(w * 0.72) :]
    sky = heatmap[: int(h * 0.35), int(w * 0.35) : int(w * 0.65)]
    return {
        "tree_mean": float(tree.mean()),
        "tree_p95": float(np.percentile(tree, 95)),
        "tree_high_frac": float((tree > 0.5).mean()),
        "sign_mean": float(sign.mean()),
        "sign_p95": float(np.percentile(sign, 95)),
        "sign_high_frac": float((sign > 0.5).mean()),
        "sky_mean": float(sky.mean()),
        "sky_p95": float(np.percentile(sky, 95)),
    }


@pytest.mark.integration
class TestCatNetOfficialExampleInput:
    def test_runtime_ready(self):
        from core.legacy.imdlbenco.cat_net_official_pipeline import official_runtime_ready

        ok, reason = official_runtime_ready()
        if not ok:
            pytest.skip(reason)
        assert ok

    @pytest.mark.skipif(not EXAMPLE.is_file(), reason="example_input.jpg ausente em uploads-dev")
    def test_pipeline_detects_tree_and_sign_regions(self):
        from core.legacy.imdlbenco.cat_net_official_pipeline import run_cat_net_official_analysis

        result = run_cat_net_official_analysis(str(EXAMPLE), threshold=0.5)
        assert result.original_size == (896, 1200)

        hm = np.array(result.heatmap_image.convert("L"), dtype=np.float32) / 255.0
        stats = _zone_stats(hm)

        assert stats["sky_mean"] < 0.01, f"Fundo deveria ser baixo (sky_mean={stats['sky_mean']:.4f})"
        assert stats["tree_p95"] >= 0.85, f"Arvore esquerda fraca (tree_p95={stats['tree_p95']:.3f})"
        assert stats["sign_p95"] >= 0.85, f"Placa direita fraca (sign_p95={stats['sign_p95']:.3f})"
        assert stats["tree_high_frac"] >= 0.03, f"Poucos pixels na arvore (frac={stats['tree_high_frac']:.3f})"
        assert stats["sign_high_frac"] >= 0.05, f"Poucos pixels na placa (frac={stats['sign_high_frac']:.3f})"
        assert stats["sign_mean"] > stats["sky_mean"] * 30
        assert stats["tree_mean"] > stats["sky_mean"] * 30

    @pytest.mark.skipif(not EXAMPLE.is_file(), reason="example_input.jpg ausente em uploads-dev")
    def test_imdlbenco_adapter_routes_to_official(self):
        from core.legacy.imdlbenco.cat_net_official_pipeline import official_runtime_ready
        from core.legacy.imdlbenco.imdlbenco_pipeline import run_imdlbenco_analysis

        ok, reason = official_runtime_ready()
        if not ok:
            pytest.skip(reason)

        result = run_imdlbenco_analysis(str(EXAMPLE), method="cat_net", threshold=0.5)
        assert result.method_id == "cat_net"
        assert result.original_size == (896, 1200)
        hm = np.array(result.heatmap_image.convert("L"), dtype=np.float32) / 255.0
        stats = _zone_stats(hm)
        assert stats["sign_p95"] >= 0.85
