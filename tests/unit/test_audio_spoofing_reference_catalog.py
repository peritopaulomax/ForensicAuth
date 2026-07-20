"""Tests for audio-spoofing reference-population hierarchical catalog."""

from __future__ import annotations

from core.audio_spoofing_lr_reference import (
    BASE_CATALOG,
    DEFAULT_VOICE_CLONE_REFERENCE,
    DETECTOR_PAPERS,
    ALL_DETECTORS,
    PopulationItem,
    ReferenceSelectionRoles,
    _filter_working_split,
    _eer_spoof_detector,
    build_generator_detector_eers,
    normalize_reference_selection,
    normalize_reference_selection_roles,
    reference_macro_catalog,
)


def test_reference_macro_catalog_structure():
    catalog = reference_macro_catalog()
    assert isinstance(catalog, list)
    assert len(catalog) == 4

    ids = [cat["id"] for cat in catalog]
    assert ids == ["asv_classic", "codec_conditions", "deepfake_challenges", "in_the_wild"]

    for cat in catalog:
        assert cat["year_range"]
        assert cat["description"]
        for base in cat["bases"]:
            assert base["description"]
            assert base["paper_title"]
            assert "generators" in base
            for generator in base["generators"]:
                assert generator["id"]
                assert generator["label"]
                assert "detector_eer_percent" in generator


def test_audio_reference_catalog_endpoint(client, auth_headers):
    response = client.get("/api/v1/analysis/audio-spoofing-reference-catalog", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "categories" in data
    assert len(data["categories"]) == 4
    assert data.get("detector_eer_order") == list(ALL_DETECTORS)
    assert len(data.get("detector_eer_labels", [])) == len(ALL_DETECTORS)
    defaults = data.get("default_reference_items", [])
    assert len(defaults) == len(DEFAULT_VOICE_CLONE_REFERENCE)
    assert defaults[0]["base_group"] == "DFADD"
    assert defaults[0]["subgroup"] == "StyleTTS2"
    assert any(item["base_group"] == "ASVspoof5" for item in defaults)
    assert not any(item["base_group"] == "CodecFake" for item in defaults)


def test_default_reference_selection_voice_clone_proxy():
    items = normalize_reference_selection(None)
    keys = {item.key for item in items}
    assert keys == {item.key for item in DEFAULT_VOICE_CLONE_REFERENCE}


def test_normalize_reference_selection_roles_legacy_items():
    roles = normalize_reference_selection_roles(
        {"items": [{"base_group": "DFADD", "subgroup": "GradTTS"}]}
    )
    assert len(roles.fit_items) == 1
    assert roles.fit_items == roles.test_items


def test_normalize_reference_selection_roles_split_fit_test():
    roles = normalize_reference_selection_roles(
        {
            "fit_items": [{"base_group": "DFADD", "subgroup": "GradTTS"}],
            "test_items": [{"base_group": "ASVspoof5", "subgroup": "flac_E_eval"}],
        }
    )
    assert roles.fit_items == (PopulationItem("DFADD", "GradTTS"),)
    assert roles.test_items == (PopulationItem("ASVspoof5", "flac_E_eval"),)
    assert roles.union_items == (
        PopulationItem("DFADD", "GradTTS"),
        PopulationItem("ASVspoof5", "flac_E_eval"),
    )


def test_filter_working_split_keeps_fit_and_test_only():
    import pandas as pd

    rows = []
    for key, y_fake, split in [
        ("DFADD/GradTTS", 0, "train_logreg"),
        ("DFADD/GradTTS", 0, "calibration_bigauss"),
        ("DFADD/GradTTS", 0, "test_bigauss"),
        ("ASVspoof5/flac_E_eval", 1, "test_bigauss"),
        ("ASVspoof5/flac_E_eval", 1, "train_logreg"),
    ]:
        base, subgroup = key.split("/", 1)
        rows.append(
            {
                "reference_key": key,
                "reference_base_group": base,
                "reference_subgroup": subgroup,
                "y_fake": y_fake,
                "reference_split": split,
            }
        )
    split = pd.DataFrame(rows)
    roles = ReferenceSelectionRoles(
        fit_items=(PopulationItem("DFADD", "GradTTS"),),
        test_items=(PopulationItem("ASVspoof5", "flac_E_eval"),),
    )
    working = _filter_working_split(split, roles)
    assert set(working["reference_split"]) == {"train_logreg", "calibration_bigauss", "test_bigauss"}
    assert len(working) == 3
    assert "DFADD/GradTTS" in set(working.loc[working["reference_split"] != "test_bigauss", "reference_key"])
    assert working.loc[working["reference_split"].eq("test_bigauss"), "reference_key"].tolist() == [
        "ASVspoof5/flac_E_eval"
    ]


def test_audio_reference_catalog_requires_auth(client):
    response = client.get("/api/v1/analysis/audio-spoofing-reference-catalog")
    assert response.status_code == 401


def test_base_catalog_covers_protocol_datasets():
    expected = {
        "ASVspoof2019_LA",
        "ASVspoof2021_LA_eval",
        "ASVspoof5",
        "CodecFake",
        "ADD2022",
        "ADD2023",
        "DFADD",
        "SONAR",
        "In-The-Wild",
        "Fake-or-Real",
        "LibriSeVoc",
    }
    assert expected.issubset(BASE_CATALOG.keys())
    for meta in BASE_CATALOG.values():
        assert meta["description"]
        assert meta["paper_title"]


def test_detector_papers_metadata():
    assert set(DETECTOR_PAPERS) == {"df_arena_1b", "sls_xlsr", "wedefense_wavlm_mhfa"}
    for meta in DETECTOR_PAPERS.values():
        assert meta["paper_title"]
        assert meta["paper_url"]
        assert meta["repo_url"]


def test_eer_spoof_detector_perfect_separation():
    import pandas as pd

    df = pd.DataFrame(
        {
            "y_fake": [0] * 50 + [1] * 50,
            "df_arena_1b_spoof_prob": [0.1] * 50 + [0.9] * 50,
        }
    )
    assert _eer_spoof_detector(df, "df_arena_1b") == 0.0


def test_reference_macro_catalog_includes_eers_when_matrix_exists():
    catalog = reference_macro_catalog()
    codec = next(
        base
        for cat in catalog
        for base in cat["bases"]
        if base["id"] == "CodecFake"
    )
    c1 = next(gen for gen in codec["generators"] if gen["id"] == "C1")
    eers = c1.get("detector_eer_percent")
    if eers is not None:
        assert len(eers) == len(ALL_DETECTORS)
        assert all(value is None or isinstance(value, (int, float)) for value in eers)
