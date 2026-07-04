# Change History — ForensicAuth

## Missão
Preservar memória evolutiva do sistema.

## Linha do Tempo

| Data | Mudança | Categoria | Evidências |
|---|---|---|---|
| 2026-06-30 | Integração do detector SAFE (KDD 2025) ao ensemble de `synthetic_image_detection`; reprocessamento da população de referência com SAFE e atualização da score matrix de calibração LR | AI / Feature / Data | `src/backend/core/legacy/synthetic_image_detection/pipeline.py`, `src/backend/core/legacy/safe/`, `src/backend/core/synthetic_lr_reference.py`, `src/frontend/src/pages/SyntheticImageDetectionAnalysis.tsx`, `src/frontend/src/config/forensicTechniqueMeta.ts`, `outputs/lr_calibration/score_matrices/lr_scores_balanced_full.csv`, `scripts/compute_safe_reference_scores.py` |
| 2026-06-29 | Melhorias pontuais na calibração LR de `synthetic_image_detection`: Tippett sem Morrison, linha vermelha na distribuição, log decimal, LR com subconjunto de detectores, salvamento de LR report/summary/plots em derivados, UI colapsada com descrições das bases | Feature / UI / AI | `src/backend/core/synthetic_lr_reference.py`, `src/backend/core/plugins/synthetic_image_detection_adapter.py`, `src/frontend/src/pages/SyntheticImageDetectionAnalysis.tsx` |
| 2026-06-29 | Análise aprofundada do pipeline `synthetic_image_detection` (ensemble HF + B-Free + Corvi2023) | Documentation / AI | `knowledge/synthetic_image_detection_pipeline.md`, `.dev-logs/multiagent-analysis/synthetic-image-detection-*.md` |
| 2026-06-29 | Alinhamento de documentação: CLIDE, SAFE, Effort, XGBoost, NPR marcados como legados/testados, não integrados ao ensemble ativo | Documentation | `docs/specs/modules/06-module-image.md`, `knowledge/ml_assets_catalog.md`, `knowledge/synthetic_image_detection_pipeline.md` |
| 2026-06-22 | Atualização da Knowledge Layer, Summary Layer e Brain Layer | Documentation | `knowledge/`, `summaries/`, `brains/` |
| 2026-06 | Refinamento de cadeia de custódia com assinatura Ed25519 e selo de caso | Security | `services/custody_signing_service.py`, `models/case.py` |
| 2026-06 | Adição de soft-delete para casos e evidências | Data | `services/case_deletion_service.py`, `services/evidence_service.py` |
| 2026-06 | Migração de perfil `analista` para `perito` | Architecture | `db_migrations.py:ensure_migrate_analista_to_perito` |
| 2026-06 | Suporte a Peritus Desktop como modo de storage | Integration | `pages/CaseDetail.tsx`, `services/peritus_bridge.py` |
| 2026-06 | Transferência de casos via VCP package | Feature | `services/case_transfer_service.py`, `case_transfer.py` |
| 2026-05 | Implementação de compartilhamento de casos viewer/editor | Feature | `services/case_share_service.py`, `case_shares.py` |
| 2026-05 | Adição de lifecycle de fechamento bilateral de casos | Feature | `services/case_lifecycle_service.py` |
| 2026-05 | Introdução de reproducibilidade com runtime manifests | Architecture | `core/reproducibility.py`, `services/job_service.py` |
| 2026-04 | Suporte a workers CPU/GPU separados com lock distribuído | Infrastructure | `docker-compose.gpu.yml`, `core/gpu_lock.py` |
| 2026-04 | Orquestração de plugins forenses via ForensicPlugin/PluginRegistry | Architecture | `core/forensic_plugin.py`, `core/plugin_registry.py` |
| 2026-03 | Integração de múltiplos detectores sintéticos (CAMO, CLIDE, DeeCLIP, etc.) | AI | `core/legacy/synthetic_image_detection/`, `core/plugins/synthetic_image_detection_adapter.py` |
| 2026-03 | Integração IMDL-BenCo hub | AI | `core/legacy/imdlbenco/`, `core/plugins/imdlbenco_adapter.py` |
| 2026-02 | Primeira estrutura FastAPI + React | Architecture | `src/backend/app/main.py`, `src/frontend/src/main.tsx` |

## Mudanças Arquiteturais Significativas

### Migração para Monólito Modular com Plugins
- Estado Anterior: Notebooks legados isolados
- Estado Atual: FastAPI monolítico com adapters padronizados
- Motivação: Consolidar técnicas forenses em plataforma unificada
- Benefícios: Reutilização, testabilidade, padronização de I/O
- Custos: Complexidade de orquestração, GPU singleton

### Cadeia de Custódia Digital
- Estado Anterior: Hashes isolados
- Estado Atual: Registros encadeados por SHA-256 e assinados Ed25519
- Motivação: Requisitos probatórios de perícia criminal
- Benefícios: Integridade, não-repudiação, auditabilidade
- Custos: Chave de assinatura requer gestão segura

### Workers CPU/GPU Separados
- Estado Anterior: Execução síncrona local
- Estado Atual: Celery com filas `celery` e `gpu`, lock distribuído Redis
- Motivação: Serializar jobs GPU e escalar CPU
- Benefícios: Throughput, estabilidade de VRAM
- Custos: Infraestrutura adicional, complexidade de deploy

## Gate

Como chegamos até aqui: evolução de notebooks forenses isolados para uma plataforma web modular com cadeia de custódia, jobs assíncronos e múltiplas técnicas de ML.

## Evidências

- Histórico de commits (`git log`)
- `db_migrations.py`
- `docs/specs/`
- `AGENTS.md`
