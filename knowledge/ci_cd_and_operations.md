# CI/CD and Operations — ForensicAuth

## Overview

ForensicAuth is deployed as containerized services (FastAPI + React + PostgreSQL + Redis + Celery workers). This document describes the operational setup.

---

## Environments

| Environment | Compose File | Purpose |
|---|---|---|
| Development | `docker-compose.yml` | Local dev with reload, default creds |
| Dev infra | `docker-compose.dev.yml` | Postgres + Redis only for dev stack |
| Production | `docker-compose.prod.yml` | Production-ready, no reload, no default secrets |
| GPU | `docker-compose.gpu.yml` | GPU worker host |

## Services

| Service | Image | Role |
|---|---|---|
| `db` | `postgres:15-alpine` | Relational database |
| `redis` | `redis:7-alpine` | Celery broker/result backend |
| `app` | `Dockerfile` / `Dockerfile.prod` | FastAPI HTTP API |
| `worker` | `Dockerfile` / `Dockerfile.prod` | Celery CPU worker |
| `frontend` | `src/frontend/Dockerfile` | React SPA served via nginx |

## Development Scripts

| Script | Purpose |
|---|---|
| `scripts/dev-stack.sh` | Start/stop full dev stack (Postgres+Redis+API+workers+frontend) |
| `scripts/dev-lan.sh` | Start backend+frontend accessible on LAN |
| `scripts/prepare-worker-bundle.sh` | Package backend for remote GPU worker deployment |
| `scripts/seed_users.py` | Create initial admin user |

## Database Migrations

- **Alembic** is the official migration tool (`alembic.ini`, `alembic/`).
- `src/backend/app/main.py` runs `alembic upgrade head` in `ENVIRONMENT=production`.
- Dev/test keep `Base.metadata.create_all()` plus legacy `db_migrations.py` helpers.

## Required Secrets (Production)

- `SECRET_KEY` — JWT signing (strong random, ≥32 chars)
- `CUSTODY_SIGNING_PRIVATE_KEY` / `CUSTODY_SIGNING_PUBLIC_KEY` — Ed25519 custody chain
- `POSTGRES_USER` / `POSTGRES_PASSWORD` — Database credentials
- `DATABASE_URL` — PostgreSQL connection string

## Build & Deploy

1. Copy `docs/deploy/ENV-PRODUCTION-TEMPLATE.md` to `.env.production`.
2. Generate custody signing key: `python scripts/generate_custody_signing_key.py`.
3. Fill `SECRET_KEY`, database credentials, `CORS_ORIGINS`.
4. Build: `docker compose -f docker-compose.prod.yml build`.
5. Run migrations: `docker compose -f docker-compose.prod.yml run --rm app alembic upgrade head` (or rely on startup).
6. Start: `docker compose -f docker-compose.prod.yml up -d`.

## Operations

- **Logs**: `docker compose -f docker-compose.prod.yml logs -f`
- **Celery workers**: `docker compose -f docker-compose.prod.yml logs -f worker`
- **GPU worker** (remote): see `docs/deploy/WORKER-REMOTE.md`
- **Backup**: Postgres volume + `uploads/`, `results/`, `derivatives/`, `peritus_cases/`
- **Cleanup**: `preview_cleanup_scheduler` runs daily at configured hour

## Notes

- `.dockerignore` excludes dev data, caches, models (mounted as volume) and documentation.
- Production image does not use `--reload`.
- CORS is restricted in production; localhost origins are rejected.
