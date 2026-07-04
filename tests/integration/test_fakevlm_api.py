"""Integracao API: FakeVLM removido das tecnicas ativas."""

from __future__ import annotations

import pytest


@pytest.mark.integration
class TestFakeVlmApiIntegration:
    def test_techniques_does_not_list_fakevlm(self, client, auth_headers):
        res = client.get("/api/v1/analysis/techniques", headers=auth_headers)
        assert res.status_code == 200
        names = {t["name"] for t in res.json()}
        assert "fakevlm" not in names
