"""Application configuration using Pydantic Settings."""

import os
from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    APP_NAME: str = "ForensicAuth Forense Digital"
    APP_VERSION: str = "0.1.0"
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
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=480)

    # Storage
    UPLOAD_DIR: str = Field(default="./uploads")
    RESULTS_DIR: str = Field(default="./results")
    DERIVATIVES_DIR: str = Field(default="./derivatives")
    JOB_PREVIEW_RETENTION_DAYS: int = Field(default=7, ge=0, le=365)
    PERITUS_CASES_DIR: str = Field(default="./peritus_cases")
    MODELS_DIR: str = Field(default="./models")

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
        # Auto-create directories
        os.makedirs(self.UPLOAD_DIR, exist_ok=True)
        os.makedirs(self.RESULTS_DIR, exist_ok=True)
        os.makedirs(self.DERIVATIVES_DIR, exist_ok=True)
        os.makedirs(self.PERITUS_CASES_DIR, exist_ok=True)
        os.makedirs(self.MODELS_DIR, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
