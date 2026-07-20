"""Unit tests for MoE-FFD plugin (TDD)."""

from __future__ import annotations

from pathlib import Path

import pytest
import torch


class TestMoeFfdRuntime:
    def test_plugin_registered(self):
        from core.plugin_registry import PluginRegistry
        from core.technique_ids import MOE_FFD

        registry = PluginRegistry()
        plugins_dir = Path(__file__).resolve().parents[2] / "src" / "backend" / "core" / "plugins"
        registry.discover_and_register(str(plugins_dir))
        assert MOE_FFD in registry.PLUGINS
        plugin = registry.PLUGINS[MOE_FFD]()
        assert plugin.supported_types == ["imagem"]

    def test_runtime_missing_weights(self, tmp_path, monkeypatch):
        from core.legacy.moe_ffd import runtime as rt

        monkeypatch.setattr(rt, "moe_ffd_vendor_dir", lambda: tmp_path / "missing_vendor")
        monkeypatch.setattr(rt, "moe_ffd_checkpoint_path", lambda: tmp_path / "missing.tar")
        ok, reason = rt.moe_ffd_runtime_status()
        assert ok is False
        assert "Vendor" in reason or "Checkpoint" in reason

    def test_runtime_ok_when_paths_exist(self, tmp_path, monkeypatch):
        from core.legacy.moe_ffd import runtime as rt

        vendor = tmp_path / "MoE-FFD"
        vendor.mkdir()
        (vendor / "ViT_MoE.py").write_text("# stub\n", encoding="utf-8")
        ckpt = tmp_path / "MoE-FFD.tar"
        ckpt.write_bytes(b"0" * 2_000_000)

        monkeypatch.setattr(rt, "moe_ffd_vendor_dir", lambda: vendor)
        monkeypatch.setattr(rt, "moe_ffd_checkpoint_path", lambda: ckpt)
        monkeypatch.setattr(
            "core.legacy.moe_ffd.face_crop.retinaface_available",
            lambda: (True, ""),
        )
        monkeypatch.setattr(
            rt,
            "inspect_moe_ffd_checkpoint",
            lambda _path=None: {"ok": True, "reason": ""},
        )
        ok, reason = rt.moe_ffd_runtime_status()
        assert ok is True
        assert reason == ""

    def test_checkpoint_health_rejects_zero_gates(self, tmp_path):
        import torch

        from core.legacy.moe_ffd.runtime import clear_checkpoint_inspect_cache, inspect_moe_ffd_checkpoint

        # Minimal fake training checkpoint with zero MoE gates (mirrors HF defect).
        sd = {
            "blocks.0.attn.LoRA_MoE.w_gate": torch.zeros(8, 2),
            "blocks.0.attn.LoRA_MoE.w_noise": torch.zeros(8, 2),
            "head.weight": torch.randn(2, 8) * 0.01,
            "head.bias": torch.zeros(2),
            "blocks.0.attn.qkv.weight": torch.randn(24, 8),
        }
        ckpt = tmp_path / "bad.tar"
        torch.save({"model_state_dict": sd, "optimizer_state_dict": {}, "epoch": 14}, ckpt)
        clear_checkpoint_inspect_cache()
        report = inspect_moe_ffd_checkpoint(ckpt)
        assert report["ok"] is False
        assert report["format"] == "training_tar"
        assert report["epoch"] == 14
        assert "gates" in report["reason"].lower() or "w_gate" in report["reason"]

    def test_checkpoint_health_accepts_trained_gates(self, tmp_path):
        import torch

        from core.legacy.moe_ffd.runtime import clear_checkpoint_inspect_cache, inspect_moe_ffd_checkpoint

        sd = {
            "blocks.0.attn.LoRA_MoE.w_gate": torch.randn(8, 2) * 0.05,
            "blocks.0.attn.LoRA_MoE.w_noise": torch.randn(8, 2) * 0.01,
            "head.weight": torch.randn(2, 8) * 0.2,
            "head.bias": torch.zeros(2),
        }
        ckpt = tmp_path / "good.pkl"
        torch.save(sd, ckpt)  # raw best-style state_dict
        clear_checkpoint_inspect_cache()
        report = inspect_moe_ffd_checkpoint(ckpt)
        assert report["ok"] is True
        assert report["format"] == "raw_state_dict"
        assert report["gate_absmax"] >= 1e-8

    def test_validate_threshold(self, monkeypatch):
        from core.plugins.moe_ffd_adapter import MoeFfdAdapter

        monkeypatch.setattr(
            "core.plugins.moe_ffd_adapter.moe_ffd_runtime_status",
            lambda: (True, ""),
        )
        plugin = MoeFfdAdapter()
        assert plugin.validate_parameters({"threshold": 0.5})[0] is True
        ok, msg = plugin.validate_parameters({"threshold": 1.5})
        assert ok is False
        assert "threshold" in msg
        ok, msg = plugin.validate_parameters({"threshold": "x"})
        assert ok is False


class TestMoeFfdPipelineContract:
    def test_softmax_class1_is_fake(self):
        from core.legacy.moe_ffd.moe_ffd_pipeline import classify_probs

        # logits favour class 1
        logits = torch.tensor([[0.1, 2.0]])
        label, fake_p, real_p = classify_probs(logits, threshold=0.5)
        assert label == "fake"
        assert fake_p > real_p
        assert fake_p >= 0.5

        logits_real = torch.tensor([[2.0, 0.1]])
        label, fake_p, real_p = classify_probs(logits_real, threshold=0.5)
        assert label == "real"
        assert real_p > fake_p

    def test_preprocess_matches_vendor_albumentations(self, tmp_path):
        """Parity with vendor/MoE-FFD/dataset.py base_transform."""
        import albumentations as alb
        import cv2
        import numpy as np
        from albumentations.pytorch.transforms import ToTensorV2

        from core.legacy.moe_ffd.moe_ffd_pipeline import preprocess_image

        rng = np.random.default_rng(0)
        rgb = rng.integers(0, 255, size=(180, 140, 3), dtype=np.uint8)
        path = tmp_path / "face.png"
        cv2.imwrite(str(path), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))

        ours = preprocess_image(path, crop_face=False)
        vendor_tf = alb.Compose(
            [
                alb.Resize(224, 224),
                alb.Normalize(mean=[0.5, 0.5, 0.5], std=[0.5, 0.5, 0.5]),
                ToTensorV2(),
            ]
        )
        loaded = cv2.cvtColor(cv2.imread(str(path)), cv2.COLOR_BGR2RGB)
        ref = vendor_tf(image=loaded)["image"].unsqueeze(0)
        assert ours.shape == ref.shape == (1, 3, 224, 224)
        assert torch.allclose(ours, ref, atol=1e-5)

    def test_analyze_mocked(self, tmp_path, monkeypatch):
        from PIL import Image

        from core.plugins.moe_ffd_adapter import MoeFfdAdapter

        monkeypatch.setattr(
            "core.plugins.moe_ffd_adapter.moe_ffd_runtime_status",
            lambda: (True, ""),
        )

        img = tmp_path / "face.png"
        Image.new("RGB", (256, 256), (180, 120, 90)).save(img)

        def fake_infer(path, *, threshold=0.5, prefer_cuda=True, crop_face=True, face_margin=1.3, face_confidence=0.6):
            return {
                "label": "fake",
                "fake_prob": 0.91,
                "real_prob": 0.09,
                "score": 0.91,
                "threshold": threshold,
                "inference_device": "cpu",
                "model_checkpoint": "MoE-FFD.tar",
                "logits": [-1.0, 2.0],
                "face_cropped": True,
                "face_confidence": 0.99,
                "face_margin": face_margin,
                "detector_bbox": {"x": 10, "y": 10, "w": 100, "h": 120},
                "crop_bbox": {"x": 0, "y": 0, "w": 140, "h": 140},
                "face_rgb": __import__("numpy").zeros((140, 140, 3), dtype="uint8"),
            }

        monkeypatch.setattr(
            "core.legacy.moe_ffd.moe_ffd_pipeline.infer",
            fake_infer,
        )

        plugin = MoeFfdAdapter()
        result = plugin.analyze(str(img), {"threshold": 0.5, "_job_staging_dir": str(tmp_path / "out")})
        assert result["success"] is True
        assert result["adapter"] == "moe_ffd"
        assert result["label"] == "fake"
        assert result["fake_prob"] == pytest.approx(0.91)
        assert Path(result["moe_ffd_result_json_path"]).is_file()
        assert Path(result["moe_ffd_summary_txt_path"]).is_file()
        assert Path(result["moe_ffd_face_crop_path"]).is_file()

    def test_face_crop_square_with_margin(self, monkeypatch):
        import numpy as np

        from core.legacy.moe_ffd import face_crop as fc

        rgb = np.full((400, 600, 3), 40, dtype=np.uint8)
        # paint a bright face-like blob (detector will be mocked)
        monkeypatch.setattr(
            fc,
            "detect_main_face_bbox",
            lambda _rgb, confidence_threshold=0.6: ([200, 100, 80, 100], 0.95),
        )
        out = fc.crop_aligned_face(rgb, margin=1.3, confidence_threshold=0.5)
        assert out["cropped"] is True
        assert out["face_rgb"].shape[0] == out["face_rgb"].shape[1]
        assert out["face_confidence"] == 0.95
        assert out["margin"] == 1.3
