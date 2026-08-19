# 03 — Mapa do repositório

## Árvore comentada

```text
VA-Suite/
├── src/backend/     # FastAPI, plugins, forensics, services, tasks, models
├── src/frontend/    # React 18 + Vite + TypeScript
├── vendor/          # Terceiros forenses — NÃO reescrever
├── models/          # Pesos ML runtime
├── reference_data/  # Catálogos LR / typicality
├── data/            # Runtime: uploads, results, derivatives, db, peritus_cases
├── alembic/         # Migrações PostgreSQL
├── config/          # Reservado; calibração LR em reference_data/
├── scripts/technique/  # Scaffold de novas técnicas
├── docs/            # Este manual + public/deploy/developer/specs
├── tests/           # unit, integration, specs MD
├── docker-compose*.yml
├── environment.yml  # conda name: forensicauth
├── requirements.txt | requirements-gpu.txt
└── AGENTS.md        # Regras absolutas do projeto
```

**Não usar na raiz:** `uploads/`, `results/` soltos — preferir `data/`. Material morto: `LIXEIRA/` (gitignored), se existir.

## Diretórios por criticidade

| Path | Criticidade | Notas |
|------|-------------|-------|
| `src/backend/`, `src/frontend/` | Crítica | Aplicação |
| `vendor/`, `forensics/` | Crítica | Algoritmos protegidos |
| `data/` | Crítica | Evidências reais |
| `models/`, `reference_data/` | Alta | ML / LR |
| `docs/specs/` | Alta | Contratos SDD |
| `tests/` | Alta | Qualidade |
| `config/` | Baixa | Scaffold de técnicas; calibração em `reference_data/` |

## Entrypoints

| O quê | Comando / arquivo |
|-------|-------------------|
| API | `uvicorn app.main:app` em `src/backend` → `app/main.py` |
| Celery | `celery -A app.celery_app worker …` → `app/celery_app.py` |
| Frontend | `npm run dev` em `src/frontend` |
| Compose | `docker-compose.yml` (+ `.prod`, `.gpu`, `.dev`) |

## Arquivos que todo contribuinte deve conhecer

| Arquivo | Por quê |
|---------|---------|
| `AGENTS.md` | Regras (custódia, forensics intocável, specs) |
| `src/backend/core/forensic_plugin.py` | Contrato de técnica |
| `src/backend/core/plugin_registry.py` | O que está ativo vs standby |
| `src/backend/services/job_service.py` | Execução |
| `src/backend/services/custody_service.py` | Cadeia |
| `src/frontend/src/config/techniqueRegistry.tsx` | UI das técnicas |
| `docs/specs/00-overview.md` | Comportamento |

## Docs humanas vs memória de agente

| Pasta | Para humanos? | Para agentes? |
|-------|---------------|---------------|
| `docs/` (este manual + public/…) | Sim | Apoio |
| `knowledge/` `summaries/` `brains/` | Não (secundário) | Sim |

## Como verificar

```bash
ls src/backend src/frontend vendor models reference_data data docs tests
conda activate forensicauth
```

## Próximo

[04 — Backend](04-backend.md)
