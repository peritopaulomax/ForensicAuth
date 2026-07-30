"""Integration: synthetic-image detector catalog exposes bibliography + repo."""

from __future__ import annotations

import pytest


@pytest.mark.integration
def test_synthetic_image_detectors_catalog(client, auth_headers):
    res = client.get("/api/v1/analysis/synthetic-image-detectors", headers=auth_headers)
    assert res.status_code == 200
    rows = res.json()
    by_id = {row["id"]: row for row in rows}
    expected = {
        "ai_image_detector_deploy",
        "sdxl_flux_detector_v1_1",
        "bfree",
        "corvi2023",
        "safe",
    }
    assert set(by_id) == expected
    for row in rows:
        assert row.get("description")
        assert row.get("paper_title")
        assert str(row.get("paper_url", "")).startswith("http")
        assert str(row.get("repo_url", "")).startswith("http")
        assert "available" in row
    assert "2412.17671" in by_id["bfree"]["paper_url"]
    assert "2211.00680" in by_id["corvi2023"]["paper_url"]
    assert "2408.06741" in by_id["safe"]["paper_url"]
