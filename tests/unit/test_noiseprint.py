"""Unit tests for Noiseprint camera fingerprint."""

import pytest


class TestNoiseprintRuntime:
    def test_repo_present(self):
        from core.legacy.noiseprint.noiseprint_runtime import noiseprint_repo_dir

        assert noiseprint_repo_dir().is_dir()

    def test_runtime_status(self):
        from core.legacy.noiseprint.noiseprint_runtime import noiseprint_runtime_status

        ok, reason = noiseprint_runtime_status()
        if ok:
            assert reason == ""
        else:
            assert reason

    def test_plugin_registered(self):
        from pathlib import Path

        from core.plugin_registry import PluginRegistry

        plugins_dir = Path(__file__).resolve().parents[2] / "src" / "backend" / "core" / "plugins"
        registry = PluginRegistry()
        registry.discover_and_register(str(plugins_dir))
        assert registry.get("noiseprint") is not None


class TestNoiseprintAdapter:
    def test_supported_types(self):
        from core.plugins.noiseprint_adapter import NoiseprintAdapter

        assert NoiseprintAdapter().supported_types == ["imagem"]


class TestNoiseprintBlind:
    def test_heatmap_normalizes_on_valid_pixels_only(self):
        import numpy as np

        from core.legacy.noiseprint.grip_blind import heatmap_float_to_rgb

        mapp = np.zeros((10, 10), dtype=np.float32)
        mapp[2:8, 2:8] = np.linspace(1.0, 5.0, 36).reshape(6, 6)
        mapp[0:2, :] = 1.0
        mapp[-2:, :] = 1.0
        valid = np.zeros((10, 10), dtype=np.float32)
        valid[2:8, 2:8] = 1.0

        rgb = heatmap_float_to_rgb(mapp, valid)
        assert tuple(rgb[0, 0]) == (120, 120, 120)
        assert tuple(rgb[5, 5]) != (120, 120, 120)
        assert rgb[5, 5, 0] > rgb[3, 3, 0]

    def test_gen_valid_mask_full_shape(self):
        import numpy as np

        from core.legacy.noiseprint.grip_blind import gen_valid_mask_full

        _, _, resize_map = __import__(
            "core.legacy.noiseprint.grip_blind", fromlist=["_ensure_grip_imports"]
        )._ensure_grip_imports()
        valid = np.ones((4, 6), dtype=bool)
        range0 = np.arange(4, dtype=np.float32)
        range1 = np.arange(6, dtype=np.float32)
        imgsize = np.array([40, 60], dtype=np.int32)
        full, frac = gen_valid_mask_full(valid, range0, range1, imgsize, resize_map)
        assert full.shape == (40, 60)
        assert 0.0 < frac <= 1.0

    def test_grip_blind_imports(self):
        from core.legacy.noiseprint.grip_blind import (
            GRIP_ROOT,
            gen_mapp_float,
            noiseprint_blind_post,
        )

        assert GRIP_ROOT.is_dir()
        get_spam, em_gu_img, resize_map = __import__(
            "core.legacy.noiseprint.grip_blind", fromlist=["_ensure_grip_imports"]
        )._ensure_grip_imports()
        assert callable(get_spam)
        assert callable(em_gu_img)
        assert callable(resize_map)

    def test_all_qf_weights_when_runtime_ok(self):
        from core.legacy.noiseprint.noiseprint_runtime import (
            EXPECTED_QFS,
            list_missing_noiseprint_weights,
            noiseprint_runtime_status,
            resolve_noiseprint_weights_dir,
        )

        ok, _ = noiseprint_runtime_status()
        if not ok:
            pytest.skip("Noiseprint runtime not fully available")
        weights = resolve_noiseprint_weights_dir()
        assert weights is not None
        assert list_missing_noiseprint_weights(weights) == []
        assert len(EXPECTED_QFS) == 51
