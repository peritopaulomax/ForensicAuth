"""Application configuration using Pydantic Settings."""

import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root: src/backend/app/config.py -> repo root (3 levels up).
_PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    APP_NAME: str = "ForensicAuth Forense Digital"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: str = Field(default="development")
    DEBUG: bool = Field(default=False)

    # Database
    DATABASE_URL: str = Field(...)

    # Redis / Celery
    REDIS_URL: str = Field(default="redis://localhost:6379/0")
    CELERY_BROKER_URL: str = Field(default="redis://localhost:6379/0")
    CELERY_RESULT_BACKEND: str = Field(default="redis://localhost:6379/0")

    # Security
    SECRET_KEY: str = Field(default="change-me-in-production-forensicauth-2026")
    ALGORITHM: str = Field(default="HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=15)
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=14)

    @model_validator(mode="after")
    def _validate_production_secrets(self):
        """Enforce secure secrets and CORS in production environments."""
        if self.ENVIRONMENT.lower() == "production":
            insecure_defaults = (
                "change-me-in-production-forensicauth-2026",
                "change-me",
                "",
            )
            if self.SECRET_KEY in insecure_defaults:
                raise ValueError(
                    "SECRET_KEY deve ser configurado com valor seguro em producao"
                )
            if not self.CUSTODY_SIGNING_PRIVATE_KEY:
                raise ValueError(
                    "CUSTODY_SIGNING_PRIVATE_KEY deve ser configurada em producao"
                )
            for origin in self.CORS_ORIGINS:
                lowered = origin.lower()
                if "localhost" in lowered or "127.0.0.1" in lowered or "::1" in lowered:
                    raise ValueError(
                        "CORS_ORIGINS nao pode conter localhost/127.0.0.1 em producao"
                    )
        return self

    # Storage (relative values resolve against repo root, never process CWD)
    UPLOAD_DIR: str = Field(default="./data/uploads")
    RESULTS_DIR: str = Field(default="./data/results")
    DERIVATIVES_DIR: str = Field(default="./data/derivatives")
    JOB_PREVIEW_RETENTION_DAYS: int = Field(default=0, ge=0, le=365)
    JOB_PREVIEW_DAILY_CLEANUP: bool = Field(default=True)
    JOB_PREVIEW_CLEANUP_HOUR: int = Field(default=2, ge=0, le=23)

    # Assinaturas PDF (pdfsig_forense) — âncora ICP-Brasil recomendada
    # Caminhos PEM/DER/P7B separados por vírgula; se vazio, usa PDF_SIG_TRUST_ANCHOR_DIR
    PDF_SIG_TRUST_ANCHORS: str = Field(default="")
    # Diretório com raízes oficiais (ex.: models/icpbrasil/raiz-v5.crt do ITI)
    PDF_SIG_TRUST_ANCHOR_DIR: str = Field(default="./models/icpbrasil")
    PDF_SIG_TZ_OFFSET: float = Field(default=-3.0)
    PDF_SIG_FETCH: bool = Field(default=False)
    PDF_SIG_REDACT: bool = Field(default=True)

    PERITUS_CASES_DIR: str = Field(default="./data/peritus_cases")
    MODELS_DIR: str = Field(default="./models")
    # LR / typicality reference populations (scores, embeddings, cache)
    REFERENCE_DATA_DIR: str = Field(default="./reference_data")
    # Heavy staging (samples/augmented) — keep outside the git tree
    REFERENCE_BUILD_DIR: str = Field(default="")
    # Immutable corpora mount (ASVspoof, GenImage, …)
    BASES_ROOT: str = Field(default="/mnt/bases")

    # Custody Ed25519 signing (optional — dev auto-generates ephemeral key)
    CUSTODY_SIGNING_KEY_ID: str = Field(default="forensicauth-ed25519-v1")
    CUSTODY_SIGNING_PRIVATE_KEY: str = Field(default="")
    CUSTODY_SIGNING_PUBLIC_KEY: str = Field(default="")

    # Process role: api | worker-cpu | worker-gpu
    FORENSICAUTH_PROCESS_ROLE: str = Field(default="api")

    # GPU
    GPU_AVAILABLE: bool = Field(default=False)
    EFFORT_WARMUP_ON_STARTUP: bool = Field(default=True)
    ML_WARMUP_ON_STARTUP: bool = Field(default=True)
    EFFORT_WARMUP_VARIANTS: str = Field(default="genimage")
    SYNTHETIC_KEEP_RESIDENT: bool = Field(default=True)
    GPU_RESIDENT_TECHNIQUES: str = Field(default="synthetic,effort,safe")
    GPU_LRU_TTL_SECONDS: int = Field(default=1800, ge=60)
    GPU_RESERVED_FUTURE_MB: int = Field(default=7000, ge=0)
    GPU_MIN_FREE_MB: int = Field(default=1500, ge=0)
    GPU_DISTRIBUTED_LOCK: bool = Field(default=True)
    GPU_LOCK_KEY: str = Field(default="forensicauth:gpu:0")
    GPU_LOCK_TTL_SECONDS: int = Field(default=3600, ge=60)

    # Paralelismo interno (joblib) — não exposto na UI; ajuste por ambiente
    JPEG_GHOSTS_N_JOBS: int = Field(default=6, ge=1, le=48)
    PRNU_LOCALIZED_N_JOBS: int = Field(default=4, ge=1, le=48)
    # 0 = auto (todos os nucleos logicos visiveis)
    COPY_MOVE_PCA_N_JOBS: int = Field(default=0, ge=0, le=64)

    # Reproducibility / Docker runtime (injected at deploy)
    FORENSICAUTH_IMAGE_TAG: str = Field(default="")
    FORENSICAUTH_IMAGE_DIGEST: str = Field(default="")
    FORENSICAUTH_WORKER_QUEUE: str = Field(default="")

    # CORS
    CORS_ORIGINS: list[str] = Field(default=["http://localhost:3000", "http://localhost:5173"])

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        from core.reference_data.paths import clear_path_cache, project_root

        def _abs(raw: str) -> Path:
            p = Path(raw).expanduser()
            if p.is_absolute():
                return p.resolve()
            # Relative paths → repo root (never process CWD / src/backend).
            return (project_root() / p).resolve()

        def _resolve_sqlite_url(url: str) -> str:
            """Make sqlite file paths absolute against the repo root."""
            prefixes = ("sqlite:///", "sqlite:////")
            if not url.startswith("sqlite:"):
                return url
            # sqlite:////abs or sqlite:///./rel or sqlite:////rel
            if url.startswith("sqlite:////"):
                # absolute already (4 slashes) or //host — leave absolute filesystem paths
                rest = url[len("sqlite:///"):]  # keeps leading /
                if rest.startswith("/"):
                    return url
            if url.startswith("sqlite:///./") or url.startswith("sqlite:////./"):
                rel = url.split("sqlite:///", 1)[1].lstrip("./")
                abs_db = (project_root() / rel).resolve()
                return f"sqlite:///{abs_db}"
            if url.startswith("sqlite:///") and not url.startswith("sqlite:////"):
                rest = url[len("sqlite:///"):]
                if rest.startswith("./") or (rest and not rest.startswith("/")):
                    abs_db = (project_root() / rest.lstrip("./")).resolve()
                    return f"sqlite:///{abs_db}"
            return url

        object.__setattr__(self, "DATABASE_URL", _resolve_sqlite_url(self.DATABASE_URL))

        upload = _abs(self.UPLOAD_DIR)
        results = _abs(self.RESULTS_DIR)
        derivatives = _abs(self.DERIVATIVES_DIR)
        peritus = _abs(self.PERITUS_CASES_DIR)
        models = _abs(self.MODELS_DIR)
        ref_data = _abs(self.REFERENCE_DATA_DIR)

        object.__setattr__(self, "UPLOAD_DIR", str(upload))
        object.__setattr__(self, "RESULTS_DIR", str(results))
        object.__setattr__(self, "DERIVATIVES_DIR", str(derivatives))
        object.__setattr__(self, "PERITUS_CASES_DIR", str(peritus))
        object.__setattr__(self, "MODELS_DIR", str(models))
        object.__setattr__(self, "REFERENCE_DATA_DIR", str(ref_data))

        anchor_dir_raw = (self.PDF_SIG_TRUST_ANCHOR_DIR or "").strip()
        if anchor_dir_raw:
            object.__setattr__(
                self, "PDF_SIG_TRUST_ANCHOR_DIR", str(_abs(anchor_dir_raw))
            )
            os.makedirs(self.PDF_SIG_TRUST_ANCHOR_DIR, exist_ok=True)

        # Auto-create directories
        os.makedirs(upload, exist_ok=True)
        os.makedirs(results, exist_ok=True)
        os.makedirs(derivatives, exist_ok=True)
        os.makedirs(peritus, exist_ok=True)
        os.makedirs(models, exist_ok=True)
        os.makedirs(ref_data, exist_ok=True)
        # Keep path helpers in sync with Settings (tests / alternate roots).
        # Always overwrite so a stale CWD-resolved value cannot stick.
        os.environ["FORENSICAUTH_REFERENCE_DATA_DIR"] = str(ref_data)
        if self.REFERENCE_BUILD_DIR.strip():
            os.environ["FORENSICAUTH_REFERENCE_BUILD_DIR"] = str(_abs(self.REFERENCE_BUILD_DIR))
        if self.BASES_ROOT.strip():
            os.environ["FORENSICAUTH_BASES_ROOT"] = str(_abs(self.BASES_ROOT))
        clear_path_cache()



@lru_cache
def get_settings() -> Settings:
    return Settings()
