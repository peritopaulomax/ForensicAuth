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
├── uploads/         # Legado local vazio; NÃO é o path canônico
├── alembic/         # Migrações PostgreSQL
├── scripts/         # Ingestão, downloads parciais, diagnóstico e scaffold
│   └── technique/   # Scaffold e exemplos YAML de novas técnicas
├── docs/            # Este manual + public/deploy/developer/specs
├── tests/           # unit, integration, specs MD
├── docker-compose*.yml
├── environment.yml  # conda name: forensicauth
├── requirements.txt | requirements-gpu.txt
└── AGENTS.md        # Regras absolutas do projeto
```

## Diretórios por criticidade

| Path | Criticidade | Notas |
|------|-------------|-------|
| `src/backend/`, `src/frontend/` | Crítica | Aplicação |
| `vendor/`, `forensics/` | Crítica | Algoritmos protegidos |
| `data/` | Crítica | Evidências reais |
| `models/`, `reference_data/` | Alta | ML / LR |
| `docs/specs/` | Alta | Contratos SDD |
| `tests/` | Alta | Qualidade |
| `scripts/` | Média | Ferramentas de contribuidores; inventário em `scripts/README.md` |

## Entrypoints

| O quê | Comando / arquivo |
|-------|-------------------|
| API | `uvicorn app.main:app` em `src/backend` → `app/main.py` |
| Celery | `celery -A app.celery_app worker …` → `app/celery_app.py` |
| Frontend | `npm run dev` em `src/frontend` |
| Compose | `docker-compose.yml` (+ `.prod`, `.gpu`, `.dev`) |
| Scaffold | `scripts/technique/scaffold_technique.py` + exemplos em `scripts/technique/examples/` |

## Arquivos que todo contribuinte deve conhecer

| Arquivo | Por quê |
|---------|---------|
| `AGENTS.md` | Regras (custódia, forensics intocável, specs) |
| `src/backend/core/forensic_plugin.py` | Contrato de técnica |
| `src/backend/core/plugin_registry.py` | Ativo vs standby |
| `src/backend/services/job_service.py` | Execução |
| `src/backend/services/custody_service.py` | Cadeia |
| `src/frontend/src/config/techniqueRegistry.tsx` | UI das técnicas |
| `docs/specs/00-overview.md` | Comportamento |


## Como verificar

```bash
ls src/backend src/frontend vendor models reference_data data docs tests scripts
conda activate forensicauth
```

`uploads/` na raiz é um resíduo local vazio. O runtime usa `data/uploads/`.

## Próximo

[04 — Backend](04-backend.md)
