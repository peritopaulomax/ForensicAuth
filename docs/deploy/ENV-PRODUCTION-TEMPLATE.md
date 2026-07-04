# ForensicAuth Production Environment Template

Copy the variables below into a `.env.production` file at the project root before running `docker compose -f docker-compose.prod.yml up`.

```bash
ENVIRONMENT=production
DEBUG=false

# Required: generate a strong secret, e.g. openssl rand -hex 32
SECRET_KEY=change-me-to-a-strong-secret-at-least-32-chars

# Required: Ed25519 key pair for custody chain signing
# Generate via: python scripts/generate_custody_signing_key.py
CUSTODY_SIGNING_PRIVATE_KEY=
CUSTODY_SIGNING_PUBLIC_KEY=

# Database
POSTGRES_USER=forensicauth
POSTGRES_PASSWORD=change-me-strong-db-password
POSTGRES_DB=forensicauth
DATABASE_URL=postgresql+psycopg2://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}

# Redis / Celery
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0

# Storage
UPLOAD_DIR=/app/uploads
RESULTS_DIR=/app/results
DERIVATIVES_DIR=/app/derivatives
PERITUS_CASES_DIR=/app/peritus_cases
MODELS_DIR=/app/models
JOB_PREVIEW_RETENTION_DAYS=0
JOB_PREVIEW_DAILY_CLEANUP=true
JOB_PREVIEW_CLEANUP_HOUR=2
HF_HUB_CACHE=/app/models/synthetic_image_detection/huggingface
TRANSFORMERS_OFFLINE=1

# GPU (set true only on GPU hosts)
GPU_AVAILABLE=false

# Parallelism
JPEG_GHOSTS_N_JOBS=6
PRNU_LOCALIZED_N_JOBS=4
COPY_MOVE_PCA_N_JOBS=0
```

## Required changes

1. Replace `SECRET_KEY` with a cryptographically secure random string.
2. Run `python scripts/generate_custody_signing_key.py` and paste the generated private/public keys.
3. Replace `POSTGRES_PASSWORD` with a strong database password.
4. Ensure `CORS_ORIGINS` in `src/backend/app/config.py` or via env is restricted to production origins.
