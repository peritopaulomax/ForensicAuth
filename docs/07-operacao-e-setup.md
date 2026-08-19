# 07 — Operação e setup

## Pré-requisitos

- Linux (produção documentada para Linux)  
- Conda (dev) ou Docker  
- PostgreSQL 15 + Redis 7 (Compose ou locais)  
- Opcional: NVIDIA + drivers para worker GPU  

## Ambiente conda (desenvolvimento)

```bash
conda env create -f environment.yml   # name: forensicauth
conda activate forensicauth
pip install -r requirements.txt
# GPU:
pip install -r requirements-gpu.txt
```

## Subir stack em desenvolvimento

### Opção A — processos manuais

1. Infra: `docker compose -f docker-compose.dev.yml up -d` (db :5433, redis :6380 — conferir arquivo).  
2. API:

```bash
cd src/backend
conda activate forensicauth
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

3. Worker CPU:

```bash
cd src/backend
celery -A app.celery_app worker -Q celery -l info
```

4. Worker GPU (outra shell, com CUDA):

```bash
export FORENSICAUTH_PROCESS_ROLE=worker-gpu
celery -A app.celery_app worker -Q gpu -c 1 -l info
```

5. Frontend: `npm run dev` em `src/frontend` (:3000).

### Opção B — Compose completo

```bash
docker compose up -d
# serviços: db, redis, app, worker, frontend
```

### Opção C — Compose GPU

```bash
docker compose -f docker-compose.gpu.yml up -d
# app + worker-cpu + worker-gpu; sem frontend — combine com FE local ou outro compose
```

Produção: [`public/INSTALACAO-PRODUCAO-LINUX.md`](public/INSTALACAO-PRODUCAO-LINUX.md), [`deploy/ENV-PRODUCTION-TEMPLATE.md`](deploy/ENV-PRODUCTION-TEMPLATE.md), `docker-compose.prod.yml`.

## Docker / Compose — o que é

| Arquivo | Papel |
|---------|-------|
| `docker-compose.yml` | Stack padrão (db, redis, app, worker, frontend) |
| `docker-compose.prod.yml` | Produção + `.env.production` |
| `docker-compose.gpu.yml` | Split CPU/GPU workers + NVIDIA |
| `docker-compose.dev.yml` | Só Postgres/Redis para dev host |
| `Dockerfile` / `Dockerfile.gpu` / `Dockerfile.prod` | Imagens |

> Calibração LR/typicality: ativos em **`reference_data/`**.

## Redis — papéis

1. **Broker Celery** e result backend  
2. **Lock de GPU** (serialização de inferência)  

Sem Redis saudável, enfileiramento em produção falha.

## Filas Celery

| Fila | Worker | Concurrency sugerida |
|------|--------|----------------------|
| `celery` | worker-cpu | >1 possível (cuidado com CPU) |
| `gpu` | worker-gpu | **`-c 1`** |

Retry / timeouts: ver `tasks/analysis_tasks.py` (limites hard distintos CPU vs GPU).

Observar fila GPU: `GET /api/v1/analysis/gpu-queue`.

Worker remoto: [`deploy/WORKER-REMOTE.md`](deploy/WORKER-REMOTE.md).

## Variáveis e segredos

| Tema | Exemplos |
|------|----------|
| DB | `DATABASE_URL` |
| Redis/Celery | `REDIS_URL`, `CELERY_BROKER_URL` |
| Paths | `UPLOAD_DIR`, `RESULTS_DIR`, `MODELS_DIR` |
| Auth | JWT secret |
| Custody | chaves Ed25519 |
| Role | `FORENSICAUTH_PROCESS_ROLE` |

**Nunca** commitar `.env` real. Use `.env.example` / `.env.production.example`.

## Scripts e automação

| Path | Função |
|------|--------|
| `scripts/technique/` | Scaffold de técnica (contribuidores) |
| Download de pesos / calibração | Ferramental do ambiente |

Infra e workers: use Compose ou os comandos manuais desta página.

## Como verificar

| Check | Comando / ação |
|-------|----------------|
| API viva | `curl http://127.0.0.1:8000/health` |
| DB | login + listar casos |
| Redis/fila | submeter job CPU e ver `running`→`completed` |
| GPU | job ML + `gpu-queue` / logs worker-gpu |
| FE | abrir :3000 ou :80 no Compose |

## Atenção

- Compose GPU sem frontend → UI “sumiu”.  
- API com role errada fazendo warmup → VRAM desperdiçada.  
- Paths de models diferentes entre API e worker → “técnica indisponível”.

## Próximo

[09 — ML e artefatos](09-ml-e-artefatos.md) ou [08 — Glossário](08-glossario-e-armadilhas.md)
