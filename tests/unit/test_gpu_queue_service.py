"""Tests for GPU queue visibility service."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import uuid4

from services.gpu_queue_service import gpu_queue_snapshot, gpu_wait_message, is_gpu_technique


class TestGpuQueueService:
    def test_is_gpu_technique(self):
        assert is_gpu_technique("synthetic_image_detection") is True
        assert is_gpu_technique("audio_spectrogram") is False

    def test_gpu_queue_snapshot_position(self):
        jid1, jid2 = uuid4(), uuid4()
        job1 = MagicMock(id=jid1, created_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
        job2 = MagicMock(id=jid2, created_at=datetime(2026, 1, 2, tzinfo=timezone.utc))

        db = MagicMock()
        query = db.query.return_value
        query.filter.return_value.order_by.return_value.all.return_value = [job1, job2]

        snap = gpu_queue_snapshot(db, job_id=jid2)
        assert snap["pending_gpu_jobs"] == 2
        assert snap["gpu_queue_position"] == 2

    def test_gpu_wait_message(self):
        assert gpu_wait_message({"gpu_queue_position": 2, "pending_gpu_jobs": 3}) == (
            "Aguardando GPU (2 de 3 na fila)"
        )
        assert gpu_wait_message({"gpu_queue_position": 1, "pending_gpu_jobs": 1}) == (
            "Aguardando worker GPU"
        )
        assert gpu_wait_message({"gpu_queue_position": None, "pending_gpu_jobs": 0}) is None
