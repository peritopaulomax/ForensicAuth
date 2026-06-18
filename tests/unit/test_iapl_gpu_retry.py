"""Unit tests for IAPL GPU retry without silent CPU fallback."""

from __future__ import annotations

from PIL import Image


class TestIaplGpuRetry:
    def test_oom_without_cpu_fallback_raises(self, monkeypatch):
        import torch

        from core.legacy.iapl import iapl_pipeline as mod

        monkeypatch.setattr(mod, "prepare_vram_for_iapl", lambda **_: {})
        monkeypatch.setattr(mod, "clear_iapl_model_cache", lambda: None)
        monkeypatch.setattr(mod, "_iapl_allow_cpu_fallback", lambda: False)
        monkeypatch.setattr(mod, "resolve_inference_device", lambda: torch.device("cuda"))

        def _boom(*_args, **_kwargs):
            raise RuntimeError("CUDA out of memory. Tried to allocate 66.00 MiB")

        monkeypatch.setattr(mod, "_run_iapl_on_device", _boom)

        with __import__("pytest").raises(RuntimeError, match="VRAM insuficiente"):
            mod._infer_iapl_with_gpu_retry(
                Image.new("RGB", (64, 64)),
                variant_id="genimage",
                on_progress=None,
                progress_pct=69,
                vram_prepared=True,
            )

    def test_cpu_fallback_when_enabled(self, monkeypatch):
        import torch

        from core.legacy.iapl import iapl_pipeline as mod

        monkeypatch.setattr(mod, "prepare_vram_for_iapl", lambda **_: {})
        monkeypatch.setattr(mod, "clear_iapl_model_cache", lambda: None)
        monkeypatch.setattr(mod, "_iapl_allow_cpu_fallback", lambda: True)
        monkeypatch.setattr(mod, "resolve_inference_device", lambda: torch.device("cuda"))

        calls: list[str] = []

        def _run(*_args, **kwargs):
            dev = kwargs["device"]
            calls.append(dev.type)
            if dev.type == "cuda":
                raise RuntimeError("CUDA out of memory")
            return 0.42

        monkeypatch.setattr(mod, "_run_iapl_on_device", _run)

        prob, device = mod._infer_iapl_with_gpu_retry(
            Image.new("RGB", (64, 64)),
            variant_id="genimage",
            on_progress=None,
            progress_pct=69,
            vram_prepared=True,
        )
        assert prob == 0.42
        assert device.type == "cpu"
        assert calls.count("cuda") == 2
