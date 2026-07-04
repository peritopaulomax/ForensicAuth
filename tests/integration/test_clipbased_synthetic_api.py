"""Integracao API: ClipBased-SyntheticImageDetection removido das tecnicas ativas."""

from __future__ import annotations

import pytest


@pytest.mark.integration
class TestClipBasedSyntheticApiIntegration:
    def test_techniques_does_not_list_clipbased_synthetic(self, client, auth_headers):
        res = client.get("/api/v1/analysis/techniques", headers=auth_headers)
        assert res.status_code == 200
        names = {t["name"] for t in res.json()}
        assert "clipbased_synthetic" not in names
