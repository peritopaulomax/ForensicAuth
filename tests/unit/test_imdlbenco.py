"""Unit tests for IMDL-BenCo hub."""

import pytest


class TestImdlBencoCatalog:
    def test_registered_methods(self):
        from core.legacy.imdlbenco.imdlbenco_catalog import IMDLBENCO_METHODS

        assert len(IMDLBENCO_METHODS) == 11
        ids = {m.id for m in IMDLBENCO_METHODS}
        assert "trufor" in ids
        assert "cat_net" in ids
        assert "objectformer" in ids
        assert "mesorch" in ids
        assert "sparse_vit" in ids
        assert "miml_apscnet" in ids
        assert "iml_vit" not in ids


class TestImdlBencoRuntime:
    def test_list_method_status(self):
        from core.legacy.imdlbenco.imdlbenco_runtime import list_method_status

        rows = list_method_status()
        assert len(rows) == 11
        assert all("status" in r and "id" in r for r in rows)

    def test_mesorch_checkpoint_names(self):
        from core.legacy.imdlbenco.imdlbenco_runtime import MESORCH_VARIANTS, list_mesorch_variants

        assert MESORCH_VARIANTS["standard"] == "mesorch-98.pth"
        assert MESORCH_VARIANTS["mesorch_p"] == "mesorch_p-118.pth"
        variants = list_mesorch_variants()
        assert len(variants) == 2

    def test_native_checkpoint_names(self):
        from core.legacy.imdlbenco.imdlbenco_runtime import CHECKPOINT_NAMES, NFA_VIT_CHECKPOINT_NAME

        assert CHECKPOINT_NAMES["trufor"] == "trufor_casiav2.pth"
        assert CHECKPOINT_NAMES["cat_net"] == "cat_net_cat_net.pth"
        assert CHECKPOINT_NAMES["objectformer"] == "object_former_casiav2.pth"
        assert NFA_VIT_CHECKPOINT_NAME == "nfa_vit_brgen.pth"

    def test_nfa_vit_status_when_vendor_present(self):
        from core.legacy.imdlbenco.imdlbenco_runtime import method_runtime_status, vendor_root

        if not (vendor_root() / "BR-Gen-main").is_dir():
            pytest.skip("vendor BR-Gen ausente")
        status, reason = method_runtime_status("nfa_vit")
        assert status in ("ready", "weights_missing", "vendor_missing")
        if status == "weights_missing":
            assert "NFA-ViT" in reason or "nfa_vit" in reason.lower() or "pesos" in reason.lower()

    def test_dinov3_iml_status_when_vendor_present(self):
        from core.legacy.imdlbenco.dinov3_iml_official_pipeline import official_runtime_ready
        from core.legacy.imdlbenco.imdlbenco_runtime import (
            DINOV3_IML_VENDOR_DIR,
            method_runtime_status,
            vendor_root,
        )

        if not (vendor_root() / DINOV3_IML_VENDOR_DIR).is_dir():
            pytest.skip("vendor DINOv3-IML ausente")
        ok, reason = official_runtime_ready()
        status, _ = method_runtime_status("dinov3_iml")
        assert status in ("ready", "weights_missing")
        if ok:
            assert status == "ready"
        else:
            assert "peso" in reason.lower() or "checkpoint" in reason.lower() or "peft" in reason.lower()

    def test_co_transformers_checkpoint_names(self):
        from core.legacy.imdlbenco.imdlbenco_runtime import CO_TRANSFORMERS_CHECKPOINT_NAMES

        assert CO_TRANSFORMERS_CHECKPOINT_NAMES[0] == "co_transformers.pth"

    def test_co_transformers_preprocess_matches_vendor_scripts(self):
        """Vendor train/test scripts use --if_resizing (not --if_padding)."""
        from core.legacy.imdlbenco.imdlbenco_catalog import get_method

        spec = get_method("co_transformers")
        assert spec is not None
        assert spec.use_resizing is True
        assert spec.use_padding is False
        assert spec.image_size == 512
        assert spec.edge_width == 7

    def test_objectformer_status_when_weights_present(self):
        from core.legacy.imdlbenco.imdlbenco_runtime import method_runtime_status, resolve_checkpoint

        ckpt = resolve_checkpoint("objectformer")
        if ckpt is None:
            pytest.skip("checkpoint ObjectFormer ausente")
        status, _ = method_runtime_status("objectformer")
        assert status == "ready"

    def test_co_transformers_status_when_vendor_present(self):
        from core.legacy.imdlbenco.co_transformers_official_pipeline import official_runtime_ready
        from core.legacy.imdlbenco.imdlbenco_runtime import (
            CO_TRANSFORMERS_VENDOR_DIR,
            method_runtime_status,
            vendor_root,
        )

        if not (vendor_root() / CO_TRANSFORMERS_VENDOR_DIR).is_dir():
            pytest.skip("vendor Co-Transformers ausente")
        ok, reason = official_runtime_ready()
        status, _ = method_runtime_status("co_transformers")
        assert status in ("ready", "weights_missing")
        if ok:
            assert status == "ready"
        else:
            assert "peso" in reason.lower() or "checkpoint" in reason.lower() or "co-transformers" in reason.lower()

    def test_miml_paths_and_status(self):
        from core.legacy.imdlbenco.imdlbenco_runtime import (
            method_runtime_status,
            miml_iml_vendor_root,
            resolve_miml_apsc_checkpoint,
        )

        assert miml_iml_vendor_root().name == "models for IML"
        assert resolve_miml_apsc_checkpoint() is None or resolve_miml_apsc_checkpoint().name == "APSC-Net.pth"
        assert method_runtime_status("miml_apscnet")[0] in ("ready", "weights_missing")


class TestImdlBencoAdapter:
    def test_validate_unknown_method(self):
        from core.plugins.imdlbenco_adapter import ImdlBencoAdapter

        adapter = ImdlBencoAdapter()
        ok, msg = adapter.validate_parameters({"method": "invalid"})
        assert not ok
        assert "method" in msg

    def test_validate_mesorch_variant(self):
        from core.plugins.imdlbenco_adapter import ImdlBencoAdapter

        adapter = ImdlBencoAdapter()
        ok, msg = adapter.validate_parameters({"method": "mesorch", "mesorch_variant": "invalid"})
        assert not ok
        assert "mesorch_variant" in msg

    def test_plugin_registered(self):
        from pathlib import Path

        from core.plugin_registry import PluginRegistry

        plugins_dir = Path(__file__).resolve().parents[2] / "src" / "backend" / "core" / "plugins"
        registry = PluginRegistry()
        registry.discover_and_register(str(plugins_dir))
        assert registry.get("imdlbenco") is not None
        assert "iml_vit" not in registry.list_plugins()

    def test_supported_types(self):
        from core.plugins.imdlbenco_adapter import ImdlBencoAdapter

        assert ImdlBencoAdapter().supported_types == ["imagem"]
