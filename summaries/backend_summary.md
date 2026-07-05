# Backend Summary — ForensicAuth

**Atualizado:** 2026-07-04

## Stack

FastAPI + SQLAlchemy + Pydantic + Celery + Redis + PostgreSQL (prod) / SQLite (dev)

## Camadas

| Camada | Path | Papel |
|---|---|---|
| App | `app/main.py`, `config.py`, `celery_app.py` | Bootstrap, settings, workers |
| API | `api/v1/endpoints/` | REST (~15 routers) |
| Services | `services/` | Domínio (jobs, custody, evidence, derivative, GPU queue) |
| Core | `core/` | Plugins, ML pipelines, reproducibility, GPU |
| Plugins | `core/plugins/` | ~35 adapters ativos |
| Legacy | `core/legacy/` | Algoritmos forenses + runtime |
| Tasks | `tasks/analysis_tasks.py` | Celery CPU/GPU |

## Técnicas canônicas (`technique_ids.py`)

- `synthetic_image_detection` (alias `sepael`)
- `presentation_attack_detection`
- `audio_spoofing_detection`

## Jobs

```text
POST /analysis → JobService → JobRunner
  → Celery (Postgres) ou thread (SQLite)
  → queue: gpu | celery
```

GPU: synthetic, safire, noiseprint, imdlbenco, videofact, stil, lfv, pad

CPU: clássicas, PDF, áudio espectral, **audio_spoofing_detection**

## Novidades jul/2026

| Módulo | Função |
|---|---|
| `audio_spoofing/` | Orquestra DF Arena, SLS, WeDefense |
| `synthetic_lr_reference.py` | LR calibrado multi-detector imagem |
| `deeclip/` | Pipeline DeeCLIP (infra; não no ensemble) |
| `wedefense_spoofing/`, `sls_spoofing/` | Detectores áudio |

## APIs novas

- `GET /analysis/audio-spoofing-detectors`
- `GET /analysis/synthetic-reference-catalog`

## Config crítica

`DATABASE_URL`, `REDIS_URL`, `FORENSICAUTH_PROCESS_ROLE`, `MODELS_DIR`, `GPU_*`, `DF_ARENA_MODEL`

## Testes

~487 unit + ~55 integration + 14 e2e backend (`tests/`)

## Riscos backend

GPU lock, torch.load inseguro, pesos locais, audio spoofing na fila CPU sob carga
