"""Phase 4 infrastructure/deployment tests.

Tests for divergences IN-01, IN-02, IN-05, IN-07.
"""

import os
from pathlib import Path

import pytest


class TestDockerComposeVolumes:
    def test_compose_cpu_includes_derivatives_and_peritus_volumes(self):
        from yaml import safe_load

        root = Path(__file__).resolve().parents[2]
        with open(root / "docker-compose.yml", encoding="utf-8") as f:
            compose = safe_load(f)

        for service in ("app", "worker"):
            envs = compose["services"][service].get("environment", [])
            env_map = {e.split("=", 1)[0]: e.split("=", 1)[1] for e in envs if "=" in e}
            assert "DERIVATIVES_DIR" in env_map
            assert "PERITUS_CASES_DIR" in env_map

            volumes = compose["services"][service].get("volumes", [])
            volume_targets = [v.split(":")[1] for v in volumes if ":" in v]
            assert "/app/derivatives" in volume_targets
            assert "/app/peritus_cases" in volume_targets


class TestCondaEnvironmentName:
    def test_scripts_use_forensicauth_conda_env(self):
        root = Path(__file__).resolve().parents[2] / "scripts"
        for script in ("dev-stack.sh", "dev-lan.sh"):
            content = (root / script).read_text(encoding="utf-8")
            assert "FORENSICAUTH_CONDA_ENV" in content
            assert ':-va-suite' not in content
            assert 'FORENSIC_AUTH_CONDA_ENV' not in content


class TestAlembic:
    def test_alembic_ini_exists(self):
        root = Path(__file__).resolve().parents[2]
        assert (root / "alembic.ini").is_file()
        assert (root / "alembic" / "env.py").is_file()

    def test_initial_revision_exists(self):
        root = Path(__file__).resolve().parents[2]
        versions = list((root / "alembic" / "versions").glob("*.py"))
        assert len(versions) > 0


class TestProductionCors:
    def test_production_rejects_localhost_cors(self, monkeypatch):
        from app.config import Settings

        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
        monkeypatch.setenv("SECRET_KEY", "strong-secret-key-at-least-32-chars-long")
        monkeypatch.setenv("CUSTODY_SIGNING_PRIVATE_KEY", "dummy-key")
        monkeypatch.setenv("CORS_ORIGINS", '["http://localhost:3000"]')

        with pytest.raises(ValueError, match="CORS_ORIGINS"):
            Settings()

    def test_production_accepts_valid_cors(self, monkeypatch):
        from app.config import Settings

        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
        monkeypatch.setenv("SECRET_KEY", "strong-secret-key-at-least-32-chars-long")
        monkeypatch.setenv("CUSTODY_SIGNING_PRIVATE_KEY", "dummy-key")
        monkeypatch.setenv("CORS_ORIGINS", '["https://forense.pf.gov.br"]')

        settings = Settings()
        assert "https://forense.pf.gov.br" in settings.CORS_ORIGINS
