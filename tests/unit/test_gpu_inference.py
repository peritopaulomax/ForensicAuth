"""Unit tests for shared GPU inference helpers."""

from unittest.mock import MagicMock, patch


class TestGpuInference:
    def test_resolve_inference_device_prefers_cuda(self):
        from core.gpu_inference import resolve_inference_device

        with patch("torch.cuda.is_available", return_value=True):
            device = resolve_inference_device()
        assert device.type == "cuda"

    def test_resolve_inference_device_cpu_fallback(self):
        from core.gpu_inference import resolve_inference_device

        with patch("torch.cuda.is_available", return_value=False):
            device = resolve_inference_device()
        assert device.type == "cpu"

    def test_is_cuda_oom_or_device_error(self):
        from core.gpu_inference import is_cuda_oom_or_device_error

        assert is_cuda_oom_or_device_error(RuntimeError("CUDA out of memory"))
        assert not is_cuda_oom_or_device_error(
            RuntimeError(
                "Input type (torch.cuda.FloatTensor) and weight type (torch.FloatTensor) should be the same"
            )
        )
        assert not is_cuda_oom_or_device_error(RuntimeError("invalid shape"))

    def test_run_with_device_fallback_retries_on_cuda_error(self):
        from core.gpu_inference import run_with_device_fallback

        calls: list[str] = []

        def run_fn(device):
            calls.append(device.type)
            if device.type == "cuda":
                raise RuntimeError("CUDA out of memory")
            return "ok"

        with patch("core.gpu_inference.resolve_inference_device") as resolve:
            resolve.return_value = MagicMock(type="cuda")
            with patch("core.gpu_inference.release_gpu_memory"):
                result, device = run_with_device_fallback(run_fn)

        assert result == "ok"
        assert device.type == "cpu"
        assert calls == ["cuda", "cpu"]

    def test_run_with_device_fallback_calls_on_before_cpu_fallback(self):
        from core.gpu_inference import run_with_device_fallback

        oom_messages: list[str] = []

        def run_fn(device):
            if device.type == "cuda":
                raise RuntimeError("CUDA out of memory")
            return "ok"

        with patch("core.gpu_inference.resolve_inference_device") as resolve:
            resolve.return_value = MagicMock(type="cuda")
            with patch("core.gpu_inference.purge_foreign_gpu_model_caches"):
                result, device = run_with_device_fallback(
                    run_fn,
                    on_before_cpu_fallback=oom_messages.append,
                )

        assert result == "ok"
        assert device.type == "cpu"
        assert len(oom_messages) == 1
        assert "out of memory" in oom_messages[0].lower()

    def test_evict_cache_keys_on_device(self):
        from core.gpu_inference import evict_cache_keys_on_device

        cache = {"trufor:cuda": object(), "trufor:cpu": object()}
        with patch("core.gpu_inference.release_gpu_memory") as release:
            evict_cache_keys_on_device(cache)
            release.assert_called()
        assert "trufor:cuda" not in cache
        assert "trufor:cpu" in cache
