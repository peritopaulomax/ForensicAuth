# Repository Map — ForensicAuth

## Missão
Explicar como o repositório ForensicAuth está organizado.

## Resumo
O repositório é um monorepo com backend Python (FastAPI), frontend React (TypeScript/Vite), documentação, testes, modelos de ML, códigos legados forenses e scripts operacionais. O deploy é feito via Docker Compose.

## Árvore Comentada

```text
ForensicAuth/
├── src/
│   ├── backend/           # API FastAPI, serviços, plugins e legados
│   └── frontend/          # SPA React + TypeScript + Vite
├── docs/                  # Documentação pública e de desenvolvedor
│   ├── specs/             # Especificações comportamentais e técnicas
│   ├── developer/         # Guias internos
│   ├── public/            # Guias de instalação e operação
│   └── deploy/            # Deploy e workers remotos
├── tests/                 # Testes unitários, integração e E2E
├── outputs/               # Artefatos de experimento/LR (NÃO versionar — .gitignore)
├── knowledge/             # Knowledge Layer (este diretório)
├── summaries/             # Summary Layer
├── brains/                # Brain Layer
├── prompts/               # Prompts de execução por módulo
├── scripts/               # Scripts de deploy, download de pesos e utilitários
├── models/                # Pesos de modelos ML (.pth, .onnx, .safetensors)
├── models-dev/            # Pesos em desenvolvimento
├── vendor/                # Códigos de terceiros (forks de detectores forenses)
├── Legados/               # Notebooks e códigos originais Peritus (C++/Qt, etc.)
├── uploads/               # Evidências enviadas (produção/dev)
├── uploads-dev/           # Evidências de desenvolvimento
├── results/               # Resultados de jobs (produção)
├── results-dev/           # Resultados de desenvolvimento
├── derivatives/           # Derivados promovidos (produção)
├── derivatives-dev/       # Derivados de desenvolvimento
├── peritus_cases/         # Casos no formato Peritus Desktop
├── data/                  # Banco SQLite/Postgres local
├── tools/                 # Ferramentas auxiliares (C++, node)
├── docker-compose*.yml    # Orquestração de containers
├── Dockerfile*            # Imagens CPU e GPU
├── requirements*.txt      # Dependências Python
└── environment.yml        # Ambiente Conda
```

## Diretórios Principais

| Diretório | Responsabilidade | Criticidade |
|---|---|---|
| `src/backend` | API, serviços, plugins, legados, jobs | Tier 0 |
| `src/frontend` | Interface web | Tier 1 |
| `docs/specs` | Especificações do sistema | Tier 1 |
| `tests` | Testes automatizados | Tier 1 |
| `models` | Pesos de modelos ML forenses (**gitignored**) | Tier 1 |
| `outputs` | Calibração LR, caches joblib, plots (**gitignored**) | Tier 2 |
| `vendor` | Códigos de terceiros não modificados | Tier 1 |
| `Legados` | Algoritmos forenses históricos | Tier 2 |
| `scripts` | Automação de deploy e download | Tier 1 |
| `prompts` | Prompts de execução modular | Tier 2 |

## Entrypoints

| Entrypoint | Arquivo | Propósito |
|---|---|---|
| Backend API | `src/backend/app/main.py` | Bootstrap FastAPI, lifespan, routers |
| Worker Celery | `src/backend/app/celery_app.py` | App Celery para workers |
| Frontend | `src/frontend/src/main.tsx` | Montagem da SPA React |
| Frontend App | `src/frontend/src/App.tsx` | Roteamento principal |

## Configurações

| Arquivo | Propósito |
|---|---|
| `src/backend/app/config.py` | Settings Pydantic |
| `.env.example` | Template de variáveis de ambiente |
| `src/backend/.env.api.example` | Config da API |
| `src/backend/.env.worker-cpu.example` | Config do worker CPU |
| `src/backend/.env.worker-gpu.example` | Config do worker GPU |
| `.env.production.example` | Config de produção |
| `docker-compose.yml` | Produção CPU |
| `docker-compose.gpu.yml` | Produção GPU |
| `docker-compose.dev.yml` | Serviços dev (Postgres/Redis) |

## Scripts Importantes

| Script | Função |
|---|---|
| `scripts/dev-stack.sh` | Orquestra ambiente dev completo |
| `scripts/dev-lan.sh` | Dev acessível na LAN |
| `scripts/prepare-worker-bundle.sh` | Sincroniza worker remoto |
| `scripts/seed_users.py` | Cria usuário admin padrão |
| `scripts/generate_custody_signing_key.py` | Gera chave Ed25519 |
| `scripts/diagnose_gpu.py` | Diagnóstico de GPU |
| `scripts/download_*_weights.py` | Download de pesos ML |

## Testes

| Local | Tipo |
|---|---|
| `tests/unit/` | Testes unitários Python |
| `tests/integration/` | Testes de integração |
| `tests/specs/` | Especificações de teste por módulo |
| `src/frontend/src/**/*.test.ts*` | Testes unitários frontend |
| `src/frontend/e2e/` | Testes E2E Playwright |

## Dependências Importantes

- FastAPI, SQLAlchemy, Pydantic, Celery, Redis
- PostgreSQL, SQLite
- React, Vite, TypeScript, Axios, Zustand
- PyTorch, OpenCV, NumPy, SciPy
- PyMuPDF, jpegio, librosa, soundfile
- IMDL-BenCo, transformers, onnxruntime

## Arquivos Críticos

- `src/backend/app/main.py`
- `src/backend/app/config.py`
- `src/backend/services/job_service.py`
- `src/backend/services/custody_service.py`
- `src/backend/core/forensic_plugin.py`
- `src/backend/core/plugin_registry.py`
- `src/frontend/src/App.tsx`
- `AGENTS.md`

## Evidências

- Estrutura listada por `find . -maxdepth 2 -type d`
- `README.md`
- `docker-compose.yml`
- `src/backend/app/main.py`
- `src/frontend/package.json`
