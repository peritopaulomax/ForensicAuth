# Plano de Ajustes — ForensicAuth

**Data:** 2026-06-25  
**Baseado em:** `/analisar-repositorio`, `/atualizar-conhecimento`, `/atualizar-cerebro`, `/detectar-divergencias`, `/saude-do-conhecimento`, `/revisar-analise`  
**Status:** Aguardando aprovação

---

## Decisões Aprovadas nas Enquetes

| Tema | Decisão |
|---|---|
| **CustodyRecord em jobs** | Não gerar. Jobs são previews exploratórios; a cadeia de custódia formal cobre apenas upload, derivados e fechamento. Atualizar specs para refletir a decisão. |
| **Infra dev vs produção** | Criar artefatos prod separados (`docker-compose.prod.yml`, `Dockerfile.prod`); manter compose/Dockerfile base como dev. |
| **Caso `fechamento_pendente`** | Bloquear análises/evidências, mas permitir assinaturas, manifestos e operações diretamente relacionadas ao fechamento. |
| **Dashboard / Laudos** | Integrar Dashboard criando rota `/dashboard`; manter Laudos/Relatórios como planejado. |
| **Alembic** | Adotar Alembic como motor oficial de migrações; criar diretório `alembic/` e remover `db_migrations.py` ad-hoc. |
| **Foco inicial** | Segurança e custódia primeiro; depois jobs, infra, frontend e catálogos. |

---

## Diretrizes Gerais

1. **Testes antes de avançar:** todo ajuste de código deve vir acompanhado de testes unitários/integração e deve passar antes da próxima fase.
2. **Mínima intrusão:** alterar apenas o necessário; preservar algoritmos forenses legados (Regra Máxima 8).
3. **Documentação acompanha código:** atualizar specs, knowledge, summaries e brain layer após cada fase.
4. **Commits por fase:** cada fase deve resultar em um conjunto coeso de alterações commitadas.

---

## Fase 1 — Segurança e Custódia Crítica

**Objetivo:** eliminar as 7 divergências críticas de segurança, permissão e custódia.

**Prazo sugerido:** 1 semana

### 1.1 Validações de permissão e caso fechado (BE-01, BE-02, BE-03)

- `src/backend/api/v1/endpoints/analysis.py`:
  - Em `submit_job`, após `get_accessible_evidence`, verificar `assert_can_edit_case` e `assert_case_not_closed`.
- `src/backend/services/job_service.py`:
  - Em `submit_job`, reforçar validação de `evidence.case.status` e permissão de edição.
- `src/backend/api/v1/endpoints/evidences.py`:
  - Em `delete_evidence`, aplicar `_require_case_mutable`.
- `src/backend/services/evidence_service.py`:
  - Em `delete_evidence`, reforçar validação de permissão/caso fechado.
- `src/backend/api/v1/endpoints/cases.py`:
  - Em `update_case`, aplicar `assert_can_edit_case`.

**Testes:** `tests/unit/test_cases.py`, `tests/unit/test_evidences.py`, `tests/unit/test_jobs.py`, novos testes de integração para submissão/exclusão em caso fechado.

### 1.2 Decisão documentada: jobs não geram CustodyRecord (FJ-01)

- Atualizar `docs/specs/modules/05-module-jobs.md` para refletir que jobs são previews e não geram CustodyRecord.
- Atualizar `knowledge/domain_model.md`, `knowledge/architecture.md` e `brains/critical_paths.md`.
- Verificar e ajustar `tests/specs/test-module-jobs.md`.

### 1.3 Secrets obrigatórios (IN-08, IN-09)

- `src/backend/app/config.py`:
  - `SECRET_KEY`: remover default fraco; em produção, falhar se não configurado.
  - `CUSTODY_SIGNING_PRIVATE_KEY`: garantir que, em produção, a chave seja configurada explicitamente.
- Criar `scripts/generate_custody_signing_key.py` (se não existir) e documentar uso.
- Atualizar `.env.example` com instruções claras.

**Testes:** testes de inicialização com/without secrets; testes de assinatura de custódia.

### 1.4 Infraestrutura de produção (IN-03, IN-06)

- Criar `Dockerfile.prod` sem `--reload`.
- Criar `docker-compose.prod.yml`:
  - Sem credenciais padrão.
  - Com volumes `derivatives` e `peritus_cases`.
  - Usando `Dockerfile.prod`.
  - Referenciando `.env.production`.
- Manter `docker-compose.yml` e `Dockerfile` base como dev.
- Adicionar `.dockerignore` (IN-04).

**Testes:** build local de `docker-compose.prod.yml` com `.env` de exemplo; validar que app inicia sem defaults inseguros.

---

## Fase 2 — Permissões e Validações de Domínio

**Objetivo:** consolidar regras de negócio na camada de serviço e corrigir bypasses.

**Prazo sugerido:** 1 semana

### 2.1 Compatibilidade técnica vs tipo de mídia (BE-05 / FJ-06)

- `src/backend/services/job_service.py`:
  - Após resolver plugin, verificar `evidence.file_type in plugin.supported_types`.
  - Retornar 422 com mensagem clara se incompatível.

**Testes:** submeter job de técnica de imagem em evidência de áudio; esperar 422.

### 2.2 Uploads de referência técnica (BE-06)

- `src/backend/api/v1/endpoints/evidences.py`:
  - Padronizar todos os endpoints de referência técnica para usar `_require_case_mutable`.

### 2.3 Validação de upload de evidência no serviço (BE-11)

- `src/backend/services/evidence_service.py`:
  - Replicar validação de caso mutável em `upload_evidence`.

### 2.4 Workflow de fechamento (BE-04, BE-12)

- `src/backend/api/v1/endpoints/cases.py`:
  - Remover `status` do `UpdateCaseRequest` (fechamento/reabertura devem usar endpoints específicos).
  - Remover tratamento legado de `"em_andamento"` após confirmar migração.

**Testes:** tentativa de update direto de status deve falhar; fechamento/reabertura apenas pelos endpoints apropriados.

---

## Fase 3 — Jobs Forenses

**Objetivo:** corrigir reproducibilidade, contratos e comportamento de técnicas.

**Prazo sugerido:** 1-2 semanas

### 3.1 `artifact_sha256` e `result_sha256` (FJ-02, FJ-12)

- Documentar semântica: `result_sha256` = hash do manifesto `result.json`; `artifact_sha256` = hash do artefato primário quando existir.
- Implementar preenchimento condicional de `artifact_sha256` via `REPRODUCIBILITY_REGISTRY`.
- Ajustar testes (`tests/unit/test_jobs.py:137`).

### 3.2 Diretório de resultados (FJ-03)

- Alterar `JobService.run_job` e todos os pontos de leitura para usar `{RESULTS_DIR}/{case_id}/{evidence_id}/{job_id}/`.
- Atualizar `DerivativeService` e endpoints de análise.

**Testes:** testes de integração verificando estrutura de diretórios.

### 3.3 Schema de técnicas (FJ-05)

- Adicionar `description` e `parameters_schema` na classe base `ForensicPlugin` e nos adapters.
- Atualizar `TechniqueResponse` e `list_techniques`.

### 3.4 Configuração de técnicas GPU (FJ-07, FJ-08)

- Remover `deepfake_similarity` de `ML_GPU_TECHNIQUES` enquanto estiver em standby.
- Atualizar `RN-JOB-01` para listar apenas técnicas realmente GPU.

### 3.5 Timeouts e stale jobs (FJ-09, FJ-10)

- Configurar `task_time_limit`/`task_soft_time_limit` por fila ou timeout manual no worker.
- Generalizar `fail_stale_pending_gpu_jobs` para jobs CPU.

---

## Fase 4 — Infraestrutura e Deploy

**Objetivo:** alinhar configuração de ambiente e adotar Alembic.

**Prazo sugerido:** 1 semana

### 4.1 Alembic (IN-05)

- Inicializar `alembic/`.
- Criar migração inicial baseada nos modelos atuais.
- Substituir chamadas de `db_migrations.py` em `main.py` por `alembic upgrade head`.
- Remover `db_migrations.py` ou mantê-lo como fallback de migração.
- Remover `alembic` de `requirements.txt`? Não — agora será usado.

### 4.2 Ambiente Conda (IN-02)

- Alinhar todos os scripts para nome único `forensicauth` e variável `FORENSICAUTH_CONDA_ENV`.

### 4.3 CORS (IN-07)

- Restringir `allow_methods` e `allow_headers` em produção.
- Manter permissivo apenas em dev via configuração.

---

## Fase 5 — Frontend

**Objetivo:** integrar Dashboard e corrigir documentação.

**Prazo sugerido:** 3-5 dias

### 5.1 Dashboard (FE-01)

- Criar rota `/dashboard` em `src/frontend/src/App.tsx`.
- Adicionar link no menu/navegação.
- Atualizar `feature_catalog.md`.

### 5.2 Métricas e rotas inexistentes (FE-02, FE-03, FE-04)

- Corrigir tamanho de `pages/` no `frontend_summary.md`.
- Reclassificar rota genérica de análise e Laudos como "Planejado".
- Atualizar `feature_catalog.md`.

---

## Fase 6 — Catálogos e Brain Layer

**Objetivo:** completar documentação operacional e alinhar camadas.

**Prazo sugerido:** 1 semana

### 6.1 Catálogos faltantes

- `knowledge/api_catalog.md`
- `knowledge/data_catalog.md`
- `knowledge/frontend_component_catalog.md`
- `knowledge/ml_assets_catalog.md`
- `knowledge/ci_cd_and_operations.md`

### 6.2 Brain Layer

- `brains/mental_model.md`: adicionar `Report`, `CaseShare`, `CaseClosureSignature` e papel `analista legacy`.
- `brains/system_brain.md`: adicionar `GPUResidency`, `ml_gpu_job_slot`, `gpu_distributed_lock`.
- `brains/executive_summary.md`: revisar priorização de riscos.

### 6.3 Métricas

- Executar `pytest --cov` e `vitest --coverage`.
- Registrar baseline no `test_strategy.md`.

---

## Fase 7 — Validação Final

**Objetivo:** garantir que os ajustes resolveram as divergências.

**Prazo sugerido:** 3-5 dias

1. Reexecutar `/detectar-divergencias`.
2. Reexecutar `/saude-do-conhecimento`.
3. Reexecutar `/revisar-analise`.
4. Atualizar `knowledge/final_gates.md`.
5. Meta: score de saúde ≥ 80 e zero divergências críticas.

---

## Cronograma Resumido

| Fase | Prazo | Entregáveis |
|---|---|---|
| 1 — Segurança e Custódia | Semana 1 | 7 divergências críticas corrigidas; docker-compose.prod.yml; Dockerfile.prod |
| 2 — Permissões e Domínio | Semana 2 | Validações centralizadas; workflow de fechamento protegido |
| 3 — Jobs Forenses | Semanas 2-3 | Reproducibilidade, diretórios, schemas e timeouts corrigidos |
| 4 — Infra e Deploy | Semana 4 | Alembic adotado; CORS/Conda alinhados |
| 5 — Frontend | Semana 4 | Dashboard integrado; documentação frontend ajustada |
| 6 — Catálogos e Brain | Semana 5 | Catálogos criados; Brain Layer completo; baseline de cobertura |
| 7 — Validação Final | Semana 5-6 | Divergências reavaliadas; score ≥ 80 |

---

## Riscos do Plano

1. **Alembic pode exigir ajustes manuais** se `db_migrations.py` tiver modificações que não estão nos modelos.
2. **Mudança no diretório de resultados (FJ-03)** pode quebrar jobs antigos se não houver migração de dados.
3. **Restrição de CORS e secrets** pode bloquear desenvolvimento local se não houver configuração dev clara.
4. **Remoção de `status` do UpdateCaseRequest** pode quebrar integrações legadas.

---

## Status de Execução

### Fase 5 — Frontend ✅ Concluída

**Data de conclusão:** 2026-06-25

**Ajustes aplicados:**
- FE-01: criada rota `/dashboard` em `App.tsx`; adicionado link no menu `Layout.tsx`.
- FE-02: rota genérica documentada como legada/redirecionada para agrupamento por mídia.
- FE-03: status de Laudos/Relatórios ajustado para "Planejada" no `feature_catalog.md`.
- FE-04: corrigido tamanho da pasta `pages/` (~18,6k linhas) e rotas no `frontend_summary.md`.

**Testes:** `tests/unit/test_phase5_frontend.py` (3 testes de verificação estrutural); build frontend não executado por indisponibilidade de Node.js no ambiente Linux.

### Fase 4 — Infraestrutura e Deploy ✅ Concluída

**Data de conclusão:** 2026-06-25

**Ajustes aplicados:**
- IN-01: adicionados volumes `derivatives` e `peritus_cases` e variáveis de ambiente no `docker-compose.yml` base.
- IN-02: scripts `dev-stack.sh`, `dev-lan.sh` e `prepare-worker-bundle.sh` alinhados para `FORENSICAUTH_CONDA_ENV` com default `forensicauth`.
- IN-05: adotado Alembic com `alembic.ini`, `alembic/env.py` e revisão inicial `20260625_initial_schema.py`; `main.py` executa `alembic upgrade head` em produção.
- IN-07: CORS restrito em produção (métodos limitados, headers controlados, rejeita localhost em `CORS_ORIGINS`).

**Testes:** 69 testes unitários relevantes passaram.

### Fase 3 — Jobs Forenses ✅ Concluída

**Data de conclusão:** 2026-06-25

**Ajustes aplicados:**
- FJ-02: `run_job` preenche `artifact_sha256` via `compute_artifact_sha256`.
- FJ-03: criado `build_job_result_dir`; `run_job`, endpoints de análise, `derivative_service.py`, `derivation_lineage.py` e `case_deletion_service.py` atualizados para usar `RESULTS_DIR/{case_id}/{evidence_id}/{job_id}/`.
- FJ-05: `ForensicPlugin` expõe `description` e `parameters_schema`; `list_techniques` e `TechniqueResponse` atualizados.
- FJ-07/FJ-08: removido `deepfake_similarity` de `ML_GPU_TECHNIQUES`; RN-JOB-01 atualizada.
- FJ-09: criadas tasks Celery `run_forensic_analysis_cpu` (10 min) e `run_forensic_analysis_gpu` (1h).
- FJ-10: generalizada função de stale jobs para CPU e GPU.

**Testes:** 63 testes unitários relevantes passaram.

**Observações:** teste `test_case_deletion.py::test_delete_case_removes_files_keeps_custody` falha preexistentemente por permissão em `/uploads`.

### Fase 2 — Permissões e Validações de Domínio ✅ Concluída

**Data de conclusão:** 2026-06-25

**Ajustes aplicados:**
- BE-05/FJ-06: `JobService.submit_job` valida `evidence.file_type in plugin.supported_types`.
- BE-06: endpoints de upload de referência técnica padronizados com `_require_case_mutable`.
- BE-11: `EvidenceService.upload_evidence` reforça validação de caso fechado.
- BE-04/BE-12: removido campo `status` de `UpdateCaseRequest`; campos extras rejeitados (`extra="forbid"`).

**Testes:** 48 testes unitários passaram (incluindo `test_phase1_security.py` e novo `test_phase2_domain.py`).

### Fase 1 — Segurança e Custódia Crítica ✅ Concluída

**Data de conclusão:** 2026-06-25

**Ajustes aplicados:**
- BE-01/BE-03: validações de permissão e caso fechado em `analysis.py`, `evidences.py`, `cases.py`.
- FJ-04: validação de caso fechado em `JobService.submit_job`.
- FJ-01: decisão documentada — jobs não geram `CustodyRecord`; specs e knowledge atualizados.
- IN-08/IN-09: `SECRET_KEY` e `CUSTODY_SIGNING_PRIVATE_KEY` obrigatórios em produção via `ENVIRONMENT=production`.
- IN-03/IN-06: criados `Dockerfile.prod`, `docker-compose.prod.yml` e `.dockerignore`; compose/Dockerfile base mantidos como dev.

**Testes:** 68 testes unitários passaram (`test_phase1_security.py`, `test_auth.py`, `test_evidence.py`, `test_case_access.py`, `test_case_lifecycle.py`, `test_jobs.py`, `test_job_dispatch.py`, `test_custody_signing.py`, `test_custody_signing_persist.py`, `test_evidence_references.py`).

**Observação:** teste pré-existente `test_audio_plugins.py::test_all_audio_plugins_registered` falha (espera 6 plugins, existem 5) — não relacionado às alterações da Fase 1.

## Próximos Passos

Iniciar **Fase 2 — Permissões e Validações de Domínio** (compatibilidade técnica vs mídia, uploads de referência, validação no serviço, workflow de fechamento).
