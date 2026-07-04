# Backend Summary — ForensicAuth

## O que é

Backend FastAPI monolítico modular para gestão forense digital.

## Stack

- Python 3.11+, FastAPI, SQLAlchemy 2.x, Pydantic v2
- Celery + Redis para jobs assíncronos
- PostgreSQL (produção), SQLite (dev/testes)
- JWT HS256 + bcrypt para auth
- Cadeia de custódia SHA-256 + assinatura Ed25519

## Estrutura

```text
app/         → bootstrap, config, DB, Celery
api/v1/      → endpoints REST
models/      → SQLAlchemy
services/    → lógica de negócio
core/        → plugins, legacy, GPU, reproducibility
tasks/       → Celery tasks
```

## Componentes críticos

- `app/main.py` — entrypoint
- `app/config.py` — settings
- `services/job_service.py` — orquestração de jobs
- `services/custody_service.py` — cadeia de custódia
- `services/custody_signing_service.py` — assinatura Ed25519
- `services/case_lifecycle_service.py` — fechamento/assinaturas
- `services/forensic_integrity_service.py` — verificação forense
- `core/forensic_plugin.py` — contrato de plugins
- `core/plugin_registry.py` — descoberta de plugins
- `core/gpu_inference.py` — fallback CPU/GPU
- `core/reproducibility.py` — manifests e recibos

## Fluxos críticos

1. Upload de evidência → hash SHA-256 → CustodyRecord
2. Submeter análise → job Celery/thread → plugin → resultado → (CustodyRecord não gerado no código atual)
3. Salvar derivado → provenance → nova evidência
4. Fechar caso → manifesto → assinaturas
5. Verificação forense → cadeia + arquivos + assinaturas

## APIs principais

- `/auth/*` — login, first-access, register
- `/users/*` — gestão de usuários
- `/cases/*` — casos, fechamento, compartilhamento
- `/evidences/*` — upload, download, derivados
- `/analysis/*` — submeter jobs, resultados, reproduzir
- `/audit/*` — verificação de cadeia e forense
- `/prnu/*` — fingerprints de câmera
- `/case-transfer/*` — export/import VCP
- `/peritus-transfer/*` — bridge Peritus Desktop

## Riscos

- SECRET_KEY padrão fraco
- JWT sem refresh token; token armazenado em `localStorage`
- CORS permissivo
- Alembic em bootstrap + migrations ad-hoc (`db_migrations.py`)
- SQLite em dev/test; produção requer PostgreSQL
- Lock de cadeia local ao processo
- Upload de referências sem permissão de edição em alguns endpoints
- `torch.load(weights_only=False)` em ~22 pipelines legados
- Imutabilidade da cadeia dependente de trigger SQLite (PG pendente)

## Dívidas

- Migrations ad-hoc coexistindo com Alembic
- Acoplamento de parâmetros por técnica
- Locks process-local para cadeia
- Observabilidade ausente
- Schemas Pydantic inline
- Módulo de laudos (Reports) modelado mas não implementado

## Confiabilidade

Alta — código bem estruturado, testes unitários extensivos.
