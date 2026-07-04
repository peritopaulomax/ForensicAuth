"""Tests for synthetic-image reference-population hierarchical catalog."""

from __future__ import annotations

from core.synthetic_lr_reference import reference_macro_catalog


def test_reference_macro_catalog_structure():
    catalog = reference_macro_catalog()
    assert isinstance(catalog, list)
    assert len(catalog) == 5

    ids = [cat["id"] for cat in catalog]
    expected = [
        "gan_older",
        "diffusion_cnn_early",
        "diffusion_cnn_modern",
        "diffusion_transformer",
        "other_neural",
    ]
    assert ids == expected

    for cat in catalog:
        assert "label" in cat
        assert "year_range" in cat
        assert "description" in cat
        assert "bases" in cat
        for base in cat["bases"]:
            assert "id" in base
            assert "label" in base
            assert "description" in base
            assert "paper_title" in base
            assert "paper_url" in base
            assert "generators" in base
            assert base["description"]
            assert base["paper_url"]
            for generator in base["generators"]:
                assert "id" in generator
                assert "label" in generator
                assert "deploy_year" in generator


def test_synthetic_reference_catalog_endpoint(client, auth_headers):
    response = client.get("/api/v1/analysis/synthetic-reference-catalog", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "categories" in data
    categories = data["categories"]
    assert len(categories) == 5
    ids = [cat["id"] for cat in categories]
    assert "gan_older" in ids
    assert "diffusion_transformer" in ids


def test_synthetic_reference_catalog_requires_auth(client):
    response = client.get("/api/v1/analysis/synthetic-reference-catalog")
    assert response.status_code == 401


def test_reference_macro_catalog_base_metadata():
    catalog = reference_macro_catalog()
    by_id = {
        base["id"]: base
        for cat in catalog
        for base in cat["bases"]
    }
    assert by_id["GenImage"]["paper_url"] == "https://arxiv.org/abs/2306.08571"
    assert by_id["BFree_extended_synthbuster"]["paper_url"] == "https://arxiv.org/abs/2412.17671"
    assert "treino" in by_id["BFree_extended_synthbuster"]["description"].lower()
