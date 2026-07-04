"""Tests for job queue dispatch and worker bootstrap."""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4


class TestJobDispatch:
    def test_synthetic_routes_gpu(self):
        from core.job_dispatch import GPU_QUEUE, queue_for_technique

        assert queue_for_technique("synthetic_image_detection") == GPU_QUEUE

    def test_ela_routes_celery(self):
        from core.job_dispatch import CPU_QUEUE, queue_for_technique

        assert queue_for_technique("ela") == CPU_QUEUE

    def test_audio_spectrogram_routes_celery(self):
        from core.job_dispatch import CPU_QUEUE, queue_for_technique

        assert queue_for_technique("audio_spectrogram") == CPU_QUEUE


class TestWorkerBootstrap:
    def test_warmup_only_worker_gpu(self, monkeypatch):
        monkeypatch.setenv("FORENSICAUTH_PROCESS_ROLE", "api")
        monkeypatch.setenv("GPU_AVAILABLE", "true")
        monkeypatch.setenv("ML_WARMUP_ON_STARTUP", "true")

        from app.config import get_settings

        get_settings.cache_clear()
        from app.worker_bootstrap import should_run_ml_warmup

        assert should_run_ml_warmup() is False
        get_settings.cache_clear()

    def test_warmup_enabled_on_worker_gpu(self, monkeypatch):
        monkeypatch.setenv("FORENSICAUTH_PROCESS_ROLE", "worker-gpu")
        monkeypatch.setenv("GPU_AVAILABLE", "true")
        monkeypatch.setenv("ML_WARMUP_ON_STARTUP", "true")

        from app.config import get_settings

        get_settings.cache_clear()
        from app.worker_bootstrap import should_run_ml_warmup

        assert should_run_ml_warmup() is True
        get_settings.cache_clear()


class TestJobRunnerRouting:
    def test_apply_async_gpu_queue(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg2://localhost/db")
        monkeypatch.setenv("FORENSICAUTH_PROCESS_ROLE", "api")

        from app.config import get_settings

        get_settings.cache_clear()

        job_id = uuid4()
        mock_job = MagicMock()
        mock_job.technique = "noiseprint"

        mock_service = MagicMock()
        mock_service.get_job.return_value = mock_job

        mock_task = MagicMock()
        mock_async = MagicMock()
        mock_task.apply_async = mock_async

        with patch("services.job_runner.SessionLocal") as session_local:
            session_local.return_value = MagicMock()
            with patch("services.job_runner.JobService", return_value=mock_service):
                with patch("tasks.analysis_tasks.run_forensic_analysis_gpu", mock_task):
                    from services.job_runner import run_job_in_background

                    run_job_in_background(job_id)

        mock_async.assert_called_once()
        assert mock_async.call_args.kwargs.get("queue") == "gpu"
        get_settings.cache_clear()
