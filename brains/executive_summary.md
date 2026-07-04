# Executive Summary — ForensicAuth

## O que é

Plataforma forense digital unificada para peritos criminais analisarem imagem, áudio, vídeo e PDF, com cadeia de custódia rastreável e laudos.

## O que entrega

- Gestão de casos periciais
- Upload de evidências com SHA-256
- Análises forenses assíncronas (CPU/GPU)
- Cadeia de custódia SHA-256 + Ed25519
- Derivados, laudos PDF e verificação forense
- Integração Peritus Desktop e VCP

## Como funciona

React SPA → FastAPI → Services → PostgreSQL/Redis/FS
                  ↓
          Celery Workers → Plugins → Legacy/Vendor/ML

## Componentes principais

| Componente | Papel |
|---|---|
| FastAPI | API REST |
| React | Interface do perito |
| PostgreSQL | Estado e custódia |
| Redis | Fila e lock GPU |
| Celery | Jobs assíncronos |
| Plugins | Adapters forenses |
| GPU Worker | Inferência ML serializada |

## Dependências principais

Python/FastAPI, PostgreSQL, Redis, PyTorch/CUDA, OpenCV, PyMuPDF, librosa, jpegio.

## Fluxos críticos

| Fluxo | Entrada | Saída |
|---|---|---|
| Upload | `POST /evidences/upload` | Evidence + CustodyRecord |
| Análise | `POST /analysis` | AnalysisJob → resultado |
| Derivado | `POST /evidences/derivatives` | Evidence derivada |
| Verificação | `GET /audit/verify-case-forensic/*` | Relatório de integridade |
| Fechamento | `POST /cases/{id}/close` | CaseClosure assinado |

## Top 5 riscos

1. GPU singleton (gargalo de throughput ML)
2. `torch.load(weights_only=False)` em ~22 pipelines
3. Credenciais padrão/SECRET_KEY fraco
4. Modelos não versionados (~43 GB)
5. Imutabilidade da cadeia dependente de trigger SQLite

## Top 5 dívidas

1. Testes de regressão forense ausentes
2. Módulo de laudos/relatórios não implementado
3. Ensemble `synthetic_image_detection`: sem score final consolidado, thresholds hardcoded
4. Validações de caso fechado/tipo de mídia incompletas
5. Migrations ad-hoc + Alembic em bootstrap / observabilidade ausente

## Confiabilidade

Alta no backend e arquitetura de custódia; média no ML/legados e frontend; requer atenção em validações de domínio.
