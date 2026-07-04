# Architecture Evolution — ForensicAuth

## Missão
Registrar evolução arquitetural do sistema.

## Estado Atual
Monólito modular FastAPI + React SPA, com persistência PostgreSQL, fila Redis/Celery, workers CPU/GPU separados, cadeia de custódia digital e dezenas de plugins forenses.

## Linha do Tempo

### v0.1 — Fundação (2026-02)
- FastAPI básico + React SPA
- Modelos User, Case, Evidence
- Upload com SHA-256

### v0.2 — Jobs e Plugins (2026-04)
- Introdução de Celery + Redis
- ForensicPlugin + PluginRegistry
- Workers CPU/GPU separados
- Lock distribuído GPU

### v0.3 — Cadeia de Custódia (2026-05)
- CustodyRecord imutável
- Assinatura Ed25519
- Selo de fechamento de caso
- Verificação forense ampliada

### v0.4 — Lifecycle e Compartilhamento (2026-06)
- Fechamento bilateral de casos
- CaseShare viewer/editor
- Soft-delete de casos/evidências
- VCP e Peritus transfer

### v0.5 — Reproducibilidade e ML (2026-06)
- Runtime manifests
- Job execution receipts
- Determinism profiles
- Integração de múltiplos detectores ML

## Mudanças Estruturais

| Mudança | De | Para | Impacto |
|---|---|---|---|
| Backend | Scripts isolados | FastAPI monolítico | Alta |
| Frontend | - | React SPA | Alta |
| Persistência | SQLite | PostgreSQL + SQLite dev | Alta |
| Fila | Síncrona | Celery + Redis | Alta |
| ML | Notebooks | Plugins + adapters | Alta |
| Custódia | Hashes simples | Cadeia encadeada + Ed25519 | Alta |
| Deploy | Manual | Docker Compose | Média |

## Deriva Arquitetural

| Aspecto | Planejado | Implementado | Divergências |
|---|---|---|---|
| Backend | FastAPI modular | FastAPI modular | Nenhuma |
| Banco | PostgreSQL + JSONB | PostgreSQL + JSONB; SQLite dev | Nenhuma |
| Fila | Celery + Redis | Celery + Redis; fallback thread SQLite | Fallback adicional |
| Frontend | React SPA | React SPA | Nenhuma |
| Migrations | Alembic | `db_migrations.py` ad-hoc | Alembic não ativo |
| Workers GPU | Múltiplas GPUs | GPU singleton | Apenas 1 GPU |
| E2E | Playwright/Cypress | Playwright (frontend) + Python | Stack misto |

## Dívida Evolutiva

| Dívida | Causa | Impacto |
|---|---|---|
| Sem Alembic | Migrações ad-hoc | Evolução de schema frágil |
| GPU singleton | Lock por processo | Gargalo de throughput |
| Frontend pages grandes | Acúmulo de funcionalidade | Manutenibilidade |
| Testes de regressão forense | Dependem de pesos grandes | Qualidade de ML |
| Observabilidade | Não priorizado | Dificuldade operacional |

## Oportunidades

| Oportunidade | Benefício | Esforço |
|---|---|---|
| Adotar Alembic | Schema versionado | Médio |
| Suporte a múltiplas GPUs | Escalar throughput GPU | Alto |
| WebSocket para status de jobs | Melhor UX em jobs longos | Médio |
| Object storage (MinIO/S3) | Desacoplar storage | Alto |
| Métricas e tracing | Observabilidade | Médio |
| CI/CD automatizado | Qualidade e deploy | Médio |

## Gate

Como a arquitetura evoluiu: de scripts/notebooks isolados para plataforma web modular com fila, cadeia de custódia e ML, mantendo legados via adapters.

## Evidências

- `docs/specs/01-architecture.md`
- `src/backend/app/db_migrations.py`
- `docker-compose*.yml`
- `src/backend/core/`
