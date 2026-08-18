"""GPU runtime: inference helpers, lock, queue, residency, VRAM.

MERGE mecânico (Fase 3e) de:
  test_gpu_inference.py
  test_gpu_lock.py
  test_gpu_queue_service.py
  test_gpu_residency.py
  test_gpu_vram_iapl.py
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

from services.gpu_queue_service import (
    STALE_PENDING_GPU_JOB_MESSAGE,
    fail_stale_pending_gpu_jobs,
    gpu_queue_snapshot,
    gpu_wait_message,
    is_gpu_technique,
)


# --- inference ---


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
                with patch("core.gpu_inference.purge_foreign_gpu_model_caches"):
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


# --- distributed lock ---


class TestGpuDistributedLock:
    def test_yields_true_when_lock_disabled(self, monkeypatch):
        monkeypatch.setenv("GPU_DISTRIBUTED_LOCK", "false")

        from app.config import get_settings

        get_settings.cache_clear()

        from core.gpu_lock import gpu_distributed_lock

        with gpu_distributed_lock() as acquired:
            assert acquired is True

        get_settings.cache_clear()

    def test_acquire_and_release_with_redis(self, monkeypatch):
        monkeypatch.setenv("GPU_DISTRIBUTED_LOCK", "true")
        monkeypatch.setenv("GPU_LOCK_KEY", "forensicauth:gpu:test")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")

        from app.config import get_settings

        get_settings.cache_clear()

        token = "gpu@test:abc12345"
        client = MagicMock()
        client.set.return_value = True
        client.get.return_value = token

        with patch("core.gpu_lock._redis_client", return_value=client):
            with patch("core.gpu_lock.worker_lock_id", return_value=token):
                from core.gpu_lock import gpu_distributed_lock

                with gpu_distributed_lock(blocking=False) as acquired:
                    assert acquired is True

                client.set.assert_called_once()
                client.delete.assert_called_once()

        get_settings.cache_clear()

    def test_non_blocking_returns_false_when_busy(self, monkeypatch):
        monkeypatch.setenv("GPU_DISTRIBUTED_LOCK", "true")

        from app.config import get_settings

        get_settings.cache_clear()

        client = MagicMock()
        client.set.return_value = False

        with patch("core.gpu_lock._redis_client", return_value=client):
            from core.gpu_lock import gpu_distributed_lock

            with gpu_distributed_lock(blocking=False) as acquired:
                assert acquired is False

            client.delete.assert_not_called()

        get_settings.cache_clear()

    def test_only_owner_deletes_lock(self, monkeypatch):
        monkeypatch.setenv("GPU_DISTRIBUTED_LOCK", "true")

        from app.config import get_settings

        get_settings.cache_clear()

        client = MagicMock()
        client.set.return_value = True
        client.get.return_value = "other-worker"

        with patch("core.gpu_lock._redis_client", return_value=client):
            from core.gpu_lock import gpu_distributed_lock

            with gpu_distributed_lock(blocking=False) as acquired:
                assert acquired is True

            client.delete.assert_not_called()

        get_settings.cache_clear()


# --- queue service ---


class TestGpuQueueService:
    def test_is_gpu_technique(self):
        assert is_gpu_technique("synthetic_image_detection") is True
        assert is_gpu_technique("audio_spectrogram") is False

    def test_gpu_queue_snapshot_position(self):
        jid1, jid2 = uuid4(), uuid4()
        now = datetime.now(timezone.utc)
        job1 = MagicMock(id=jid1, created_at=now)
        job2 = MagicMock(id=jid2, created_at=now)

        db = MagicMock()
        query = db.query.return_value
        query.filter.return_value.order_by.return_value.all.return_value = [job1, job2]

        snap = gpu_queue_snapshot(db, job_id=jid2)
        assert snap["pending_gpu_jobs"] == 2
        assert snap["gpu_queue_position"] == 2
        assert snap["stale_gpu_jobs_failed"] == 0

    def test_fail_stale_pending_gpu_jobs_marks_old_entries_failed(self):
        now = datetime(2026, 6, 25, 12, 0, tzinfo=timezone.utc)
        stale = MagicMock(
            status="pending",
            technique="safire",
            created_at=now - timedelta(hours=25),
        )
        fresh = MagicMock(
            status="pending",
            technique="safire",
            created_at=now - timedelta(hours=1),
        )

        db = MagicMock()
        query = db.query.return_value
        query.filter.return_value.filter.return_value.all.return_value = [stale, fresh]

        assert fail_stale_pending_gpu_jobs(db, now=now) == 1
        assert stale.status == "failed"
        assert stale.error_message == STALE_PENDING_GPU_JOB_MESSAGE
        assert fresh.status == "pending"
        db.commit.assert_called_once()

    def test_gpu_wait_message(self):
        assert gpu_wait_message({"gpu_queue_position": 2, "pending_gpu_jobs": 3}) == (
            "Aguardando GPU (2 de 3 na fila)"
        )
        assert gpu_wait_message({"gpu_queue_position": 1, "pending_gpu_jobs": 1}) == (
            "Aguardando worker GPU"
        )
        assert gpu_wait_message({"gpu_queue_position": None, "pending_gpu_jobs": 0}) is None


# --- residency ---


class TestGpuResidency:
    def test_should_keep_synthetic_when_flag_true(self, monkeypatch):
        monkeypatch.setenv("SYNTHETIC_KEEP_RESIDENT", "true")
        monkeypatch.setenv("GPU_RESIDENT_TECHNIQUES", "synthetic,effort,safe")

        from app.config import get_settings

        get_settings.cache_clear()
        from core.gpu_residency import should_keep_resident

        assert should_keep_resident("synthetic_image_detection") is True
        get_settings.cache_clear()

    def test_maybe_evict_skips_when_resident_and_ok(self, monkeypatch):
        monkeypatch.setenv("SYNTHETIC_KEEP_RESIDENT", "true")

        from app.config import get_settings

        get_settings.cache_clear()

        with patch("core.gpu_residency.vram_under_pressure", return_value=False):
            with patch("core.gpu_inference.purge_foreign_gpu_model_caches") as purge:
                from core.gpu_residency import maybe_evict_for_job

                maybe_evict_for_job("synthetic_image_detection")
                purge.assert_not_called()

        get_settings.cache_clear()


# --- vram prep ---


class TestPrepareVramForHeavyModel:
    def test_prepare_vram_calls_clear_caches(self, monkeypatch):
        calls: list[str] = []

        monkeypatch.setattr(
            "forensics.effort.effort_pipeline.clear_effort_model_cache",
            lambda: calls.append("effort"),
        )
        monkeypatch.setattr(
            "forensics.safe.safe_pipeline.clear_safe_model_cache",
            lambda: calls.append("safe"),
        )
        monkeypatch.setattr(
            "forensics.synthetic_image_detection.pipeline.release_gpu_memory",
            lambda: calls.append("synthetic"),
        )
        monkeypatch.setattr(
            "core.gpu_inference.cuda_memory_snapshot",
            lambda: {"free_mb": 1000, "total_mb": 10240, "allocated_mb": 500},
        )
        monkeypatch.setattr("core.gpu_inference.purge_foreign_gpu_model_caches", MagicMock())
        monkeypatch.setattr("core.gpu_inference.release_gpu_memory", MagicMock())

        from core.gpu_inference import prepare_vram_for_heavy_model

        result = prepare_vram_for_heavy_model(log=False)

        assert set(calls) == {"effort", "safe", "synthetic"}
        assert "before" in result and "after" in result


class TestCapImageForResidue:
    def test_small_image_unchanged(self):
        from forensics.synthetic_image_detection.pipeline import _cap_image_for_residue
        from PIL import Image

        img = Image.new("RGB", (800, 600))
        assert _cap_image_for_residue(img).size == (800, 600)

    def test_large_image_scaled_down(self):
        from forensics.synthetic_image_detection.pipeline import _cap_image_for_residue
        from PIL import Image

        img = Image.new("RGB", (4000, 3000))
        out = _cap_image_for_residue(img, max_side=2048)
        assert max(out.size) == 2048


class TestImdlGpuCachePurge:
    def test_clear_gpu_model_cache_drops_official_pipeline_caches(self, monkeypatch):
        from forensics.imdlbenco import imdlbenco_pipeline as hub
        from forensics.imdlbenco import mesorch_official_pipeline as mesorch
        from forensics.imdlbenco import miml_official_pipeline as miml

        monkeypatch.setattr(hub, "release_gpu_memory", MagicMock())
        monkeypatch.setattr(hub, "evict_cache_keys_on_device", MagicMock())

        miml._apsc_cache["cuda:0"] = object()
        mesorch._model_cache["mesorch:cuda"] = object()
        hub._model_cache["hub:cuda"] = object()

        hub._clear_gpu_model_cache()

        assert miml._apsc_cache == {}
        assert mesorch._model_cache == {}
