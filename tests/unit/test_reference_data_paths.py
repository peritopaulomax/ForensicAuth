"""Contrato de paths: runtime = REFERENCE_DATA_DIR (publish only).

Fase 5 — REVISE: o caminho feliz do produto é catalog/populations/features/cache.
BUILD / bases / samples são staging de calibração (ops), não runtime.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from core.reference_data import catalog_loader as cat
from core.reference_data import paths as rd_paths


@pytest.fixture(autouse=True)
def _clear_root_cache():
    rd_paths.clear_path_cache()
    cat.clear_catalog_cache()
    yield
    rd_paths.clear_path_cache()
    cat.clear_catalog_cache()


# --- publish root ---


def test_project_root_is_repo():
    root = rd_paths.project_root()
    assert (root / "src" / "backend").is_dir()
    assert (root / "AGENTS.md").is_file() or (root / "README.md").is_file()


def test_reference_data_root_default(monkeypatch):
    monkeypatch.delenv("FORENSICAUTH_REFERENCE_DATA_DIR", raising=False)
    monkeypatch.delenv("REFERENCE_DATA_DIR", raising=False)
    rd_paths.clear_path_cache()
    root = rd_paths.get_reference_data_root()
    assert root == (rd_paths.project_root() / "reference_data").resolve()


def test_relative_reference_data_dir_uses_project_root(monkeypatch):
    """uvicorn cwd=src/backend must not resolve ./reference_data under backend/."""
    monkeypatch.chdir(rd_paths.project_root() / "src" / "backend")
    monkeypatch.setenv("FORENSICAUTH_REFERENCE_DATA_DIR", "./reference_data")
    rd_paths.clear_path_cache()
    root = rd_paths.get_reference_data_root()
    assert root == (rd_paths.project_root() / "reference_data").resolve()
    assert "src/backend/reference_data" not in str(root).replace("\\", "/")


def test_heals_misresolved_backend_reference_data(monkeypatch):
    wrong = rd_paths.project_root() / "src" / "backend" / "reference_data"
    wrong.mkdir(parents=True, exist_ok=True)
    (wrong / "cache").mkdir(exist_ok=True)
    monkeypatch.setenv("FORENSICAUTH_REFERENCE_DATA_DIR", str(wrong))
    rd_paths.clear_path_cache()
    root = rd_paths.get_reference_data_root()
    assert root == (rd_paths.project_root() / "reference_data").resolve()


def test_settings_resolves_reference_data_from_repo_root(monkeypatch):
    monkeypatch.chdir(rd_paths.project_root() / "src" / "backend")
    monkeypatch.delenv("FORENSICAUTH_REFERENCE_DATA_DIR", raising=False)
    monkeypatch.setenv("REFERENCE_DATA_DIR", "./reference_data")
    from app.config import Settings

    s = Settings()
    assert "src/backend/reference_data" not in s.REFERENCE_DATA_DIR.replace("\\", "/")
    assert s.REFERENCE_DATA_DIR.endswith("reference_data")
    rd_paths.clear_path_cache()
    assert rd_paths.get_reference_data_root() == Path(s.REFERENCE_DATA_DIR).resolve()


def test_ensure_reference_layout_publish_only(tmp_path, monkeypatch):
    monkeypatch.setenv("FORENSICAUTH_REFERENCE_DATA_DIR", str(tmp_path))
    rd_paths.clear_path_cache()
    root = rd_paths.ensure_reference_layout()
    assert (root / "audio_spoofing" / "features" / "scores").is_dir()
    assert (root / "audio_spoofing" / "catalog").is_dir()
    assert (root / "audio_spoofing" / "populations").is_dir()
    assert (root / "synthetic_image" / "features" / "representations").is_dir()
    assert (root / "cache").is_dir()
    # Publish tree must not scaffold staging samples under reference_data.
    assert not (root / "audio_spoofing" / "working").exists()
    assert not (root / "audio_spoofing" / "samples").exists()
    assert not (root / "synthetic_image" / "working").exists()
    assert not (root / "synthetic_image" / "samples").exists()


def test_runtime_feature_paths_live_under_publish_root(tmp_path, monkeypatch):
    monkeypatch.setenv("FORENSICAUTH_REFERENCE_DATA_DIR", str(tmp_path))
    # Even if BUILD is set, score/repr/cache stay under publish.
    monkeypatch.setenv("FORENSICAUTH_REFERENCE_BUILD_DIR", str(tmp_path / "staging"))
    rd_paths.clear_path_cache()
    pub = tmp_path.resolve()
    for path in (
        rd_paths.audio_score_matrix(),
        rd_paths.audio_augmented_score_matrix(),
        rd_paths.audio_representations_matrix(),
        rd_paths.synthetic_score_matrix(),
        rd_paths.synthetic_augmented_score_matrix(),
        rd_paths.synthetic_representations_matrix(),
        rd_paths.lr_cache_dir(),
        rd_paths.audio_features_scores_dir(),
        rd_paths.synthetic_features_scores_dir(),
    ):
        assert Path(path).resolve().is_relative_to(pub)
        assert "staging" not in str(path)


def test_lr_modules_default_matrices_are_publish_paths():
    from core import audio_spoofing_lr_reference as audio_lr
    from core import synthetic_lr_reference as synth_lr

    for p in (
        audio_lr.DEFAULT_SCORE_MATRIX,
        audio_lr.DEFAULT_AUGMENTED_SCORE_MATRIX,
        synth_lr.DEFAULT_SCORE_MATRIX,
        synth_lr.DEFAULT_REPRESENTATIONS_MATRIX,
    ):
        text = str(p).replace("\\", "/")
        assert "reference_data" in text
        assert "features" in text
        assert "outputs/lr_calibration" not in text
        assert "working/samples" not in text


def test_cache_dir_resolves_under_reference_data():
    cache = rd_paths.lr_cache_dir()
    assert cache.name == "cache"
    assert "reference_data" in str(cache).replace("\\", "/") or cache.exists()


# --- catalog (publish) ---


def test_load_macros_from_repo_yaml():
    from core.audio_spoofing_lr_reference import PopulationItem, REFERENCE_MACRO_CATEGORIES

    loaded = cat.load_macros(
        "audio_spoofing",
        item_factory=PopulationItem,
        fallback_macros={},
        fallback_bases={},
    )
    assert loaded.source == "yaml"
    assert "asv_classic" in loaded.macros
    assert loaded.macros["asv_classic"]["items"]
    assert "asv_classic" in REFERENCE_MACRO_CATEGORIES


def test_register_base_updates_macros_yaml(tmp_path, monkeypatch):
    from core.audio_spoofing_lr_reference import PopulationItem

    monkeypatch.setenv("FORENSICAUTH_REFERENCE_DATA_DIR", str(tmp_path))
    rd_paths.clear_path_cache()
    cat.clear_catalog_cache()
    (tmp_path / "audio_spoofing" / "catalog").mkdir(parents=True)
    seed = {
        "version": 1,
        "domain": "audio_spoofing",
        "macros": {},
        "bases": {},
    }
    (tmp_path / "audio_spoofing" / "catalog" / "macros.yaml").write_text(
        yaml.safe_dump(seed), encoding="utf-8"
    )
    path = cat.register_base_in_macros_yaml(
        "audio_spoofing",
        base_id="NewBase",
        label="New Base",
        generators=["G1", "G2"],
        macro_id="custom",
        macro_label="Custom",
    )
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert doc["bases"]["NewBase"]["generators"] == ["G1", "G2"]
    assert len(doc["macros"]["custom"]["items"]) == 2
    loaded = cat.load_macros(
        "audio_spoofing",
        item_factory=PopulationItem,
        fallback_macros={},
    )
    assert loaded.source == "yaml"
    assert "custom" in loaded.macros


def test_voice_clone_population_yaml_loads():
    items = cat.population_as_dicts("audio_spoofing", "voice_clone_default")
    assert len(items) >= 5
    assert any(i["base_group"] == "DFADD" for i in items)


def test_audio_refresh_from_disk_returns_yaml():
    from core import audio_spoofing_lr_reference as audio_lr

    assert audio_lr.refresh_reference_catalog_from_disk() == "yaml"


# --- staging helpers (ops only; not runtime happy path) ---


def test_staging_roots_respect_env(monkeypatch, tmp_path):
    """BUILD/bases existem para calibração; não misturam com publish."""
    build = tmp_path / "build"
    bases = tmp_path / "bases"
    monkeypatch.setenv("FORENSICAUTH_REFERENCE_BUILD_DIR", str(build))
    monkeypatch.setenv("FORENSICAUTH_BASES_ROOT", str(bases))
    rd_paths.clear_path_cache()
    assert rd_paths.get_reference_build_root() == build.resolve()
    assert rd_paths.get_bases_root() == bases.resolve()


def test_ensure_build_layout_is_outside_publish(tmp_path, monkeypatch):
    pub = tmp_path / "publish"
    build = tmp_path / "build"
    monkeypatch.setenv("FORENSICAUTH_REFERENCE_DATA_DIR", str(pub))
    monkeypatch.setenv("FORENSICAUTH_REFERENCE_BUILD_DIR", str(build))
    rd_paths.clear_path_cache()
    root = rd_paths.ensure_build_layout()
    assert root == build.resolve()
    assert (root / "audio_spoofing" / "samples" / "augmented").is_dir()
    assert not (pub / "audio_spoofing" / "samples").exists()


def test_staging_sample_helpers_resolve_under_build(tmp_path, monkeypatch):
    """Samples/inventory de calibração vivem no BUILD, não em reference_data."""
    pub = tmp_path / "publish"
    build = tmp_path / "build"
    monkeypatch.setenv("FORENSICAUTH_REFERENCE_DATA_DIR", str(pub))
    monkeypatch.setenv("FORENSICAUTH_REFERENCE_BUILD_DIR", str(build))
    rd_paths.clear_path_cache()
    rd_paths.ensure_reference_layout()
    rd_paths.ensure_build_layout()
    (build / "audio_spoofing" / "samples" / "marker.txt").write_text("y", encoding="utf-8")
    (build / "synthetic_image" / "samples" / "marker.txt").write_text("y", encoding="utf-8")
    (build / "audio_spoofing" / "inventory" / "marker.txt").write_text("y", encoding="utf-8")

    audio = rd_paths.audio_samples_root().resolve()
    synth = rd_paths.synthetic_samples_root().resolve()
    inv = rd_paths.audio_inventory_dir().resolve()
    assert audio.is_relative_to(build.resolve())
    assert synth.is_relative_to(build.resolve())
    assert inv.is_relative_to(build.resolve())
    assert not audio.is_relative_to(pub.resolve())
    assert not synth.is_relative_to(pub.resolve())
