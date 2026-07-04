# Infra Summary — ForensicAuth

## O que é

Ambiente de deploy e operação para desenvolvimento e produção da plataforma forense.

## Docker

- `Dockerfile` — API/worker CPU com `--reload` (dev)
- `Dockerfile.gpu` — worker GPU com CUDA 12.4
- `src/frontend/Dockerfile` — Nginx multi-stage
- `docker-compose.yml` — stack CPU base (usa `Dockerfile` com reload)
- `docker-compose.dev.yml` — Postgres/Redis dev isolados (portas 5433/6380)
- `docker-compose.gpu.yml` — produção com GPU (inclui variáveis de residência/LRU/warmup)

## Scripts

- `dev-stack.sh` — dev completo (API + workers + frontend)
- `dev-lan.sh` — dev simples acessível na LAN
- `prepare-worker-bundle.sh` — sincroniza worker remoto via rsync
- `seed_users.py` — usuário admin (destrutivo em produção)
- `generate_custody_signing_key.py` — Ed25519
- `download_*_weights.py` — downloads de modelos
- `diagnose_gpu.py` — diagnóstico de GPU

## Configurações

- `.env.example`, `.env.production.example`
- `src/backend/.env.{api,worker-cpu,worker-gpu}.example`
- `environment.yml` (conda)
- `src/backend/app/config.py` (fonte da verdade)

## Banco

- PostgreSQL 15 (produção)
- SQLite (dev/testes)
- Schema criado por `Base.metadata.create_all()`
- Evolução por `db_migrations.py` ad-hoc
- `alembic` está em `requirements.txt` mas não é usado operacionalmente

## Fila

- Celery + Redis
- Filas `celery` (CPU) e `gpu` (ML/GPU)
- Lock distribuído Redis para GPU (`forensicauth:gpu:0`)
- Variáveis GPU: `GPU_DISTRIBUTED_LOCK`, `GPU_RESIDENT_TECHNIQUES`, `GPU_LRU_TTL_SECONDS`, `GPU_RESERVED_FUTURE_MB`, `GPU_MIN_FREE_MB`, `SYNTHETIC_KEEP_RESIDENT`, `EFFORT_WARMUP_ON_STARTUP`, `SAFE_WARMUP_ON_STARTUP`, `CUDA_VISIBLE_DEVICES`

## Storage

- Filesystem local (volumes Docker/bind mounts)
- Diretórios: uploads, results, derivatives, models, peritus_cases
- Worker remoto via NFS

## Testes

- Backend: pytest (unit, integration, e2e)
- Frontend: Vitest + Playwright
- Especificações: `tests/specs/` (13 arquivos)

## Documentação

- `docs/specs/` — SDD
- `docs/developer/` — guia de contribuição
- `docs/public/` — operação e instalação
- `docs/deploy/` — worker remoto

## Riscos

- `.dockerignore` criado, mas Dockerfile base ainda usa `--reload`
- `docker-compose.yml` base não inclui worker GPU por padrão
- Credenciais padrão em docker-compose
- Chave Ed25519 dev auto-gerada se não configurada
- SPOFs: PostgreSQL, Redis, filesystem, GPU
- Nginx frontend sem `client_max_body_size`
- Ambiente conda divergente (`forensicauth` vs `va-suite`)

## Dívidas

- Alembic em bootstrap + migrations ad-hoc
- Imagem de produção dedicada (Dockerfile base com reload)
- CI/CD não observado
- Observabilidade ausente (métricas, logs estruturados, alertas)
- Backup automatizado não versionado no repositório

## Confiabilidade

Média — funciona em dev, mas requer ajustes para produção robusta.
