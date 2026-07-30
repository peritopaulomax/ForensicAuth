"""Runtime storage vive em data/ (fora do codigo-fonte)."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_data_runtime_dirs_exist():
    for name in ("uploads", "results", "derivatives", "db", "peritus_cases"):
        assert (REPO / "data" / name).is_dir(), name


def test_no_legacy_runtime_names_at_repo_root():
    for name in (
        "uploads-dev",
        "results-dev",
        "derivatives-dev",
        "peritus_cases-dev",
        "vasuite_dev.db",
    ):
        assert not (REPO / name).exists(), name


def test_dev_db_under_data_only():
    db = REPO / "data" / "db" / "vasuite_dev.db"
    assert db.is_file()
    assert not (REPO / "vasuite_dev.db").exists()


def test_settings_resolve_storage_against_repo_root(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./data/db/vasuite_dev.db")
    monkeypatch.setenv("UPLOAD_DIR", "./data/uploads")
    monkeypatch.setenv("RESULTS_DIR", "./data/results")
    monkeypatch.setenv("DERIVATIVES_DIR", "./data/derivatives")
    monkeypatch.setenv("PERITUS_CASES_DIR", "./data/peritus_cases")
    monkeypatch.setenv("MODELS_DIR", str(REPO / "models"))
    from app.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    assert Path(settings.UPLOAD_DIR) == (REPO / "data" / "uploads").resolve()
    assert Path(settings.RESULTS_DIR) == (REPO / "data" / "results").resolve()
    assert "data/db/vasuite_dev.db" in settings.DATABASE_URL.replace("\\", "/")
    assert Path(settings.DATABASE_URL.replace("sqlite:///", "")).is_file()
    get_settings.cache_clear()
