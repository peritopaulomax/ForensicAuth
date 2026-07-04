"""Integration tests for multi-detector audio spoofing."""

from __future__ import annotations

import uuid

import numpy as np
import pytest
from scipy.io import wavfile


@pytest.fixture
def short_wav(tmp_path):
    path = tmp_path / "tone.wav"
    sr = 16000
    t = np.linspace(0, 4, sr * 4, endpoint=False)
    signal = (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    wavfile.write(path, sr, (signal * 32767).astype(np.int16))
    return str(path)


@pytest.mark.integration
class TestAudioSpoofingMultiDetectorIntegration:
    def test_audio_spoofing_detectors_catalog(self, client, auth_headers):
        res = client.get("/api/v1/analysis/audio-spoofing-detectors", headers=auth_headers)
        assert res.status_code == 200
        rows = res.json()
        ids = {row["id"] for row in rows}
        assert "df_arena_1b" in ids
        assert "sls_xlsr" in ids
        assert "wedefense_wavlm_mhfa" in ids

    def test_sls_runtime_status_when_weights_present(self):
        from core.legacy.sls_spoofing.sls_runtime import (
            resolve_sls_checkpoint_path,
            resolve_xlsr_weights_path,
            runtime_status,
        )

        if resolve_xlsr_weights_path() is None or resolve_sls_checkpoint_path() is None:
            pytest.skip("Pesos SLS nao baixados neste ambiente")
        ok, reason = runtime_status()
        assert ok, reason

    def test_sls_infer_short_audio(self, short_wav):
        from core.legacy.sls_spoofing.sls_pipeline import infer_sls_windows
        from core.legacy.sls_spoofing.sls_runtime import (
            resolve_sls_checkpoint_path,
            resolve_xlsr_weights_path,
        )

        if resolve_xlsr_weights_path() is None or resolve_sls_checkpoint_path() is None:
            pytest.skip("Pesos SLS nao baixados neste ambiente")

        import librosa

        audio, sr = librosa.load(short_wav, sr=None, mono=True)
        result = infer_sls_windows(audio, sr, window_seconds=4.0, device="cpu")
        assert result["window_count"] >= 1
        assert "aggregated" in result
        assert 0.0 <= result["aggregated"]["spoof_prob"] <= 1.0

    def test_wedefense_runtime_status_when_weights_present(self):
        from core.legacy.wedefense_spoofing.wedefense_runtime import (
            resolve_avg_checkpoint_path,
            resolve_pruned_upstream_path,
            runtime_status,
        )

        if resolve_avg_checkpoint_path() is None or resolve_pruned_upstream_path() is None:
            pytest.skip("Pesos WeDefense nao baixados neste ambiente")
        ok, reason = runtime_status()
        assert ok, reason

    def test_wedefense_infer_short_audio(self, short_wav):
        from core.legacy.wedefense_spoofing.wedefense_pipeline import infer_wedefense_windows
        from core.legacy.wedefense_spoofing.wedefense_runtime import (
            resolve_avg_checkpoint_path,
            resolve_pruned_upstream_path,
        )

        if resolve_avg_checkpoint_path() is None or resolve_pruned_upstream_path() is None:
            pytest.skip("Pesos WeDefense nao baixados neste ambiente")

        import librosa

        audio, sr = librosa.load(short_wav, sr=None, mono=True)
        result = infer_wedefense_windows(audio, sr, window_seconds=4.0, device="cpu")
        assert result["window_count"] >= 1
        assert "aggregated" in result
        assert 0.0 <= result["aggregated"]["spoof_prob"] <= 1.0
        assert 0.0 <= result["aggregated"]["bonafide_prob"] <= 1.0

    def test_post_analysis_job_multi_detector_mocked(
        self, client, auth_headers, db_session, sample_case, test_user, short_wav, monkeypatch
    ):
        from pathlib import Path

        from models.evidence import Evidence

        wav_path = Path(short_wav)
        evidence = Evidence(
            id=uuid.uuid4(),
            case_id=sample_case.id,
            filename="tone.wav",
            original_filename="tone.wav",
            file_path=str(wav_path),
            file_size=wav_path.stat().st_size,
            file_type="audio",
            mime_type="audio/wav",
            sha256="c" * 64,
            uploaded_by=test_user.id,
        )
        db_session.add(evidence)
        db_session.commit()

        def _fake_analyze(_self, _job, _evidence, progress_reporter=None, staging_dir=None):
            return {
                "success": True,
                "adapter": "audio_spoofing_detection",
                "status": "completed",
                "individual_results": [
                    ["DF Arena 1B", "0.6", "0.4", "-0.18", "Incerto", "cpu"],
                    ["SLS XLS-R (ACM MM 2024)", "0.6", "0.4", "-0.18", "Incerto", "cpu"],
                ],
                "detector_scores": {
                    "df_arena_1b": {"spoof_prob": 0.6, "bonafide_prob": 0.4, "label": "uncertain"},
                    "sls_xlsr": {"spoof_prob": 0.6, "bonafide_prob": 0.4, "label": "uncertain"},
                },
                "selected_analyses": ["df_arena_1b", "sls_xlsr"],
                "inference_device": "cpu",
                "label": "uncertain",
                "score_spoof": 0.6,
                "score_bonafide": 0.4,
                "window_count": 1,
                "detector_scores_filename": "detector_scores.txt",
            }

        monkeypatch.setattr(
            "services.job_service.JobService._execute_plugin_analysis",
            _fake_analyze,
        )
        monkeypatch.setattr("api.v1.endpoints.analysis.run_job_in_background", lambda _job_id: None)

        create = client.post(
            "/api/v1/analysis",
            headers=auth_headers,
            json={
                "evidence_id": str(evidence.id),
                "technique": "audio_spoofing_detection",
                "parameters": {"selected_analyses": ["df_arena_1b", "sls_xlsr"], "window_seconds": 4.0},
            },
        )
        assert create.status_code == 201, create.text
        job_id = create.json()["job_id"]

        from services.job_service import JobService

        JobService(db_session).run_job(uuid.UUID(job_id))
        db_session.expire_all()

        detail = client.get(f"/api/v1/analysis/{job_id}", headers=auth_headers)
        assert detail.status_code == 200
        assert detail.json()["status"] == "completed"

        result = client.get(f"/api/v1/analysis/{job_id}/result", headers=auth_headers)
        assert result.status_code == 200
        body = result.json()
        assert body.get("success") is True
        assert len(body.get("individual_results", [])) == 2
        assert body.get("detector_scores_filename") == "detector_scores.txt"
