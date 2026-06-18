"""Tests for distributed GPU lock via Redis."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


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
