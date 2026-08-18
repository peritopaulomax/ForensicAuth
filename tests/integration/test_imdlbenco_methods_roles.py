"""Integracao API: disponibilidade de metodos IMDL-BenCo por perfil."""

from __future__ import annotations

import pytest


@pytest.mark.integration
class TestImdlBencoMethodsRoleFiltering:
    def test_perito_sees_only_public_imdl_methods(self, client, auth_headers):
        res = client.get("/api/v1/analysis/imdlbenco/methods", headers=auth_headers)
        assert res.status_code == 200
        ids = {m["id"] for m in res.json()}
        assert ids >= {"cat_net", "trufor", "miml_apscnet"}
        assert "nfa_vit" not in ids
        assert "mesorch" not in ids
        assert "dinov3_iml" not in ids
        assert "co_transformers" not in ids
        assert "sparse_vit" not in ids

    def test_admin_sees_restricted_imdl_methods(self, client, admin_auth_headers):
        res = client.get("/api/v1/analysis/imdlbenco/methods", headers=admin_auth_headers)
        assert res.status_code == 200
        ids = {m["id"] for m in res.json()}
        assert "miml_apscnet" in ids
        assert "nfa_vit" in ids
        assert "mesorch" in ids
        assert "dinov3_iml" in ids

    def test_perito_cannot_submit_admin_only_imdl_method(
        self, client, auth_headers, db_session, sample_case, sample_evidence, monkeypatch
    ):
        monkeypatch.setattr("api.v1.endpoints.analysis.run_job_in_background", lambda _job_id: None)

        create = client.post(
            "/api/v1/analysis",
            headers=auth_headers,
            json={
                "evidence_id": str(sample_evidence.id),
                "technique": "imdlbenco",
                "parameters": {"method": "mesorch"},
            },
        )
        assert create.status_code == 403
        assert "administrador" in create.json()["detail"].lower()

    def test_perito_cannot_submit_safire(
        self, client, auth_headers, db_session, sample_case, sample_evidence, monkeypatch
    ):
        monkeypatch.setattr("api.v1.endpoints.analysis.run_job_in_background", lambda _job_id: None)

        create = client.post(
            "/api/v1/analysis",
            headers=auth_headers,
            json={
                "evidence_id": str(sample_evidence.id),
                "technique": "safire",
                "parameters": {"mode": "binary"},
            },
        )
        assert create.status_code == 403
        assert "administrador" in create.json()["detail"].lower()

    @pytest.mark.parametrize(
        "technique",
        ["videofact", "stil_video_detection", "lowres_fake_video", "truvil", "vilocal"],
    )
    def test_perito_cannot_submit_admin_only_video_techniques(
        self, client, auth_headers, db_session, sample_case, sample_evidence, monkeypatch, technique
    ):
        monkeypatch.setattr("api.v1.endpoints.analysis.run_job_in_background", lambda _job_id: None)

        create = client.post(
            "/api/v1/analysis",
            headers=auth_headers,
            json={
                "evidence_id": str(sample_evidence.id),
                "technique": technique,
                "parameters": {},
            },
        )
        assert create.status_code == 403
        assert "administrador" in create.json()["detail"].lower()

    def test_perito_can_submit_miml_apscnet(self, client, auth_headers, db_session, sample_case, sample_evidence, monkeypatch):
        from forensics.imdlbenco import imdlbenco_runtime

        monkeypatch.setattr("api.v1.endpoints.analysis.run_job_in_background", lambda _job_id: None)
        monkeypatch.setattr(
            imdlbenco_runtime,
            "method_runtime_status",
            lambda _method_id: ("weights_missing", "Pesos ausentes"),
        )

        create = client.post(
            "/api/v1/analysis",
            headers=auth_headers,
            json={
                "evidence_id": str(sample_evidence.id),
                "technique": "imdlbenco",
                "parameters": {"method": "miml_apscnet"},
            },
        )
        # Se os pesos nao estiverem disponiveis, o adapter retorna erro de runtime.
        # O importante e que a requisicao NAO seja bloqueada com 403 por perfil.
        assert create.status_code != 403

    def test_perito_can_submit_trufor(self, client, auth_headers, db_session, sample_case, sample_evidence, monkeypatch):
        from forensics.imdlbenco import imdlbenco_runtime

        monkeypatch.setattr("api.v1.endpoints.analysis.run_job_in_background", lambda _job_id: None)
        monkeypatch.setattr(
            imdlbenco_runtime,
            "method_runtime_status",
            lambda _method_id: ("weights_missing", "Pesos ausentes"),
        )

        create = client.post(
            "/api/v1/analysis",
            headers=auth_headers,
            json={
                "evidence_id": str(sample_evidence.id),
                "technique": "imdlbenco",
                "parameters": {"method": "trufor"},
            },
        )
        assert create.status_code != 403
