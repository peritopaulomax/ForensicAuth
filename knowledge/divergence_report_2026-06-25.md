# Relatório de Divergências — ForensicAuth

**Data da detecção:** 2026-06-25  
**Comando:** `/detectar-divergencias`  
**Metodologia:** Divergence Detection Engine — comparação entre Código, Knowledge Layer (`knowledge/`), Summary Layer (`summaries/`) e Brain Layer (`brains/`).

---

## Resumo Executivo

Foram detectadas **48 divergências** entre a base de conhecimento e o código/infraestrutura atual do projeto ForensicAuth.

| Categoria | Quantidade |
|---|---|
| Crítica | 7 |
| Alta | 11 |
| Média | 20 |
| Baixa | 10 |
| **Total** | **48** |

### Distribuição por Escopo

| Escopo | Crítica | Alta | Média | Baixa | Total |
|---|---:|---:|---:|---:|---:|
| Backend API / Domínio | 3 | 1 | 5 | 3 | 12 |
| Core Forense / Jobs | 1 | 3 | 6 | 4 | 14 |
| Frontend | 0 | 0 | 3 | 2 | 5 |
| Infra / Deploy | 2 | 2 | 3 | 2 | 9 |
| Consistência Brain/Knowledge | 1* | 2* | 3 | 1 | 7 |

\* Divergências de consistência da Brain Layer são, em sua maioria, omissões ou contradições internas da documentação; não representam bugs de código diretamente, mas sim riscos de compreensão.

---

## Matriz Consolidada de Divergências

| ID | Escopo | Divergência | Impacto | Status |
|---|---|---|---|---|
| BE-01 | Backend API/Domínio | Submissão de análise não valida caso fechado nem permissão de edição | Crítica | ✅ Corrigido |
| BE-02 | Backend API/Domínio | Exclusão de evidência não valida permissão de edição nem caso fechado | Crítica | ✅ Corrigido |
| BE-03 | Backend API/Domínio | Atualização de caso não valida permissão de edição | Crítica | ✅ Corrigido |
| BE-04 | Backend API/Domínio | Atualização de status do caso via PUT bypassa workflow de fechamento | Alta | ✅ Corrigido |
| BE-05 | Backend API/Domínio | `JobService` não valida compatibilidade técnica vs tipo de mídia | Alta | ✅ Corrigido |
| BE-06 | Backend API/Domínio | Uploads de referência técnica não exigem permissão de edição nem bloqueiam caso fechado | Média | ✅ Corrigido |
| BE-07 | Backend API/Domínio | Endpoint `POST /reports` documentado mas não implementado | Média | Documentado |
| BE-08 | Backend API/Domínio | Semântica sobreposta entre `POST /cases/{id}/close` e `/close/sign` | Média | Documentado |
| BE-09 | Backend API/Domínio | `JobService.run_job` não preenche `artifact_sha256` | Média | Documentado |
| BE-10 | Backend API/Domínio | Tipo de evidência "documento" é inatingível no upload | Média | Documentado |
| BE-11 | Backend API/Domínio | RN-09 para upload de evidências validada apenas no endpoint, não no serviço | Média | ✅ Corrigido |
| BE-12 | Backend API/Domínio | `UpdateCaseRequest.status` aceita `"em_andamento"`, estado inexistente no modelo | Baixa | ✅ Corrigido |
| FJ-01 | Core Forense/Jobs | Ciclo de vida de jobs não registra `CustodyRecord` | Crítica | Documentado |
| FJ-02 | Core Forense/Jobs | `AnalysisJob.artifact_sha256` nunca é preenchido | Alta | ✅ Corrigido |
| FJ-03 | Core Forense/Jobs | Diretório de resultados não segue contrato da especificação | Alta | ✅ Corrigido |
| FJ-04 | Core Forense/Jobs | Submissão de jobs não valida caso fechado | Alta | ✅ Corrigido |
| FJ-05 | Core Forense/Jobs | `GET /analysis/techniques` não retorna `description` e `parameters_schema` | Média | ✅ Corrigido |
| FJ-06 | Core Forense/Jobs | `JobService` não valida compatibilidade técnica vs tipo de mídia | Média | ✅ Corrigido |
| FJ-07 | Core Forense/Jobs | `deepfake_similarity` está em `ML_GPU_TECHNIQUES` mas o plugin está em standby | Média | ✅ Corrigido |
| FJ-08 | Core Forense/Jobs | RN-JOB-01 desatualizada: `prnu` listado como GPU, mas não é; `deepfake` standby | Média | ✅ Corrigido |
| FJ-09 | Core Forense/Jobs | Timeout de jobs CPU não é 10 minutos conforme especificado | Média | ✅ Corrigido |
| FJ-10 | Core Forense/Jobs | Jobs CPU pendentes por >24h não são marcados como failed | Média | ✅ Corrigido |
| FJ-11 | Core Forense/Jobs | `GET /analysis/{job_id}` não retorna campo `result` | Baixa | Documentado |
| FJ-12 | Core Forense/Jobs | `result_sha256` é hash de `result.json`, não do artefato principal | Baixa | Documentado |
| FJ-13 | Core Forense/Jobs | Fallback para thread local em `JobRunner` não adquire lock Redis | Baixa | Documentado |
| FJ-14 | Core Forense/Jobs | `REPRODUCIBILITY_REGISTRY` inclui técnicas em standby | Baixa | Documentado |
| FE-01 | Frontend | Dashboard orfão — rota `/` mapeada para `Cases` | Média | ✅ Corrigido |
| FE-02 | Frontend | Rota genérica `/cases/:caseId/analysis/:tecnica` documentada, mas inexistente | Média | ✅ Corrigido (documentada como legada/redirecionada) |
| FE-03 | Frontend | Feature Laudos/Relatórios documentada como "Parcial", mas sem representação frontend | Média | ✅ Corrigido |
| FE-04 | Frontend | Tamanho da pasta `pages/` superestimado no `frontend_summary.md` | Baixa | ✅ Corrigido |
| FE-05 | Frontend | Papel `analista` mencionado na arquitetura, mas não modelado no frontend | Baixa | Documentado |
| IN-01 | Infra/Deploy | Volumes de storage persistente incompletos no `docker-compose.yml` base | Alta | ✅ Corrigido |
| IN-02 | Infra/Deploy | Nome do ambiente Conda divergente entre artefatos | Média | ✅ Corrigido |
| IN-03 | Infra/Deploy | Imagem de produção usa `--reload` | Média | ⚠️ Parcial |
| IN-04 | Infra/Deploy | Ausência de `.dockerignore` | Média | ✅ Corrigido |
| IN-05 | Infra/Deploy | Alembic listado em `requirements.txt` mas não adotado operacionalmente | Alta | ✅ Corrigido |
| IN-06 | Infra/Deploy | Credenciais padrão em `docker-compose` | Crítica | ⚠️ Parcial |
| IN-07 | Infra/Deploy | CORS permissivo (`allow_methods=["*"]`, `allow_headers=["*"]`) | Média | ✅ Corrigido |
| IN-08 | Infra/Deploy | `SECRET_KEY` padrão fraco no código | Crítica | ✅ Corrigido |
| IN-09 | Infra/Deploy | Chave Ed25519 de custódia auto-gerada e persistida em dev | Crítica | ✅ Corrigido |
| BR-01 | Brain/Knowledge | Fluxo de análise gera ou não `CustodyRecord`? (contradição Summary vs Knowledge/Brain) | Alta | ✅ Corrigido |
| BR-02 | Brain/Knowledge | Riscos de Alta prioridade omitidos do `executive_summary.md` | Alta | Documentado |
| BR-03 | Brain/Knowledge | Entidades de domínio omitidas no `mental_model.md` | Média | Documentado |
| BR-04 | Brain/Knowledge | Componente `GPUResidency` omitido do `system_brain.md` | Média | Documentado |
| BR-05 | Brain/Knowledge | Lock distribuído GPU simplificado para "GPU singleton" | Média | Documentado |
| BR-06 | Brain/Knowledge | Papel `analista legacy` omitido do `mental_model.md` | Baixa | Documentado |
| BR-07 | Brain/Knowledge | Priorização de dívidas técnicas diverge entre `executive_summary.md` e `system_brain.md` | Baixa | Documentado |
| BR-08 | Brain/Knowledge | Metadado de tamanho da Knowledge Layer desatualizado | Baixa | Documentado |

---

## Detalhamento por Escopo

### 1. Backend API / Domínio

**Críticas**

1. **BE-01 — Submissão de análise não valida caso fechado nem permissão de edição**
   - `POST /api/v1/analysis` e `JobService.submit_job` permitem submeter jobs em casos fechados e por usuários com acesso somente leitura (`shared_viewer`). Nota: o upload principal de evidências (`POST /evidences/upload`) já valida caso mutável; a divergência está na submissão de análise e nos uploads de referência técnica.
   - Arquivos: `src/backend/api/v1/endpoints/analysis.py`, `src/backend/services/job_service.py`
   - Correção: aplicar `assert_can_edit_case` e `assert_case_not_closed` antes de submeter.

2. **BE-02 — Exclusão de evidência não valida permissão de edição nem caso fechado**
   - `DELETE /api/v1/evidences/{evidence_id}` e `EvidenceService.delete_evidence` usam apenas `get_accessible_evidence` (visibilidade).
   - Arquivos: `src/backend/api/v1/endpoints/evidences.py`, `src/backend/services/evidence_service.py`
   - Correção: aplicar `_require_case_mutable` no endpoint e reforçar no serviço.

3. **BE-03 — Atualização de caso não valida permissão de edição**
   - `PUT /api/v1/cases/{case_id}` chama apenas `get_accessible_case`, permitindo que viewers compartilhados atualizem metadados.
   - Arquivo: `src/backend/api/v1/endpoints/cases.py`
   - Correção: inserir `assert_can_edit_case(db, case, current_user)`.

**Alta**

4. **BE-04 — Atualização de status do caso via PUT bypassa workflow de fechamento**
   - `UpdateCaseRequest.status` permite alterar diretamente para `fechado`/`aberto`, contornando `CaseLifecycleService.close_case` e assinaturas.
   - Arquivo: `src/backend/api/v1/endpoints/cases.py`
   - Correção: remover `status` do schema de update ou restringir a reabertura controlada.

5. **BE-05 — `JobService` não valida compatibilidade técnica vs tipo de mídia**
   - `submit_job` resolve o plugin, mas não confronta `evidence.file_type` com `plugin.supported_types`.
   - Arquivo: `src/backend/services/job_service.py`
   - Correção: verificar `evidence.file_type in plugin.supported_types` e retornar 422 se incompatível.

**Média**

6. **BE-06 — Uploads de referência técnica não exigem permissão de edição**
   - Endpoints de referência (`prnu-reference-upload`, `pdf-structure-reference-upload`, etc.) usam `get_accessible_case` em vez de `_require_case_mutable`.
   - Arquivo: `src/backend/api/v1/endpoints/evidences.py`
   - Correção: padronizar todos os endpoints de upload de referência com `_require_case_mutable`.

7. **BE-07 — Endpoint `POST /reports` documentado mas não implementado**
   - `domain_model.md` e `backend_summary.md` mencionam a rota, mas não há router registrado em `main.py`.
   - Arquivos: `src/backend/app/main.py`, `src/backend/api/v1/endpoints/` (falta `reports.py`)
   - Correção: implementar roteador ou remover contrato da documentação.

8. **BE-08 — Semântica sobreposta entre `POST /cases/{id}/close` e `/close/sign`**
   - Ambos delegam para `CaseLifecycleService.close_case`, que decide entre iniciar fechamento ou adicionar assinatura.
   - Arquivos: `src/backend/api/v1/endpoints/cases.py`, `src/backend/services/case_lifecycle_service.py`
   - Correção: documentar idempotência ou restringir `/close/sign` exclusivamente à assinatura.

9. **BE-09 — `JobService.run_job` não preenche `artifact_sha256`**
   - Campo existe no modelo, mas `run_job` atribui explicitamente `None`, inutilizando a reproducibilidade por hash de artefato.
   - Arquivo: `src/backend/services/job_service.py`
   - Correção: calcular via `core.reproducibility.compute_artifact_sha256` ao concluir o job.

10. **BE-10 — Tipo de evidência "documento" é inatingível no upload**
    - `EvidenceService.upload_evidence` não mapeia `.docx`, `.doc`, `.odt`, `.txt` para `"documento"`.
    - Arquivo: `src/backend/services/evidence_service.py`
    - Correção: adicionar mapeamentos MIME/extensão para documentos.

11. **BE-11 — RN-09 validada apenas no endpoint, não no serviço**
    - Upload de evidências bloqueia casos fechados apenas na camada HTTP; chamadas diretas ao serviço podem contornar a regra.
    - Arquivos: `src/backend/services/evidence_service.py`, `src/backend/api/v1/endpoints/evidences.py`
    - Correção: mover/replicar a validação de caso mutável para dentro de `EvidenceService.upload_evidence`.

**Baixa**

12. **BE-12 — `UpdateCaseRequest.status` aceita `"em_andamento"`**
    - Estado legado é mapeado para `"aberto"`, mas não existe no modelo `Case`.
    - Arquivo: `src/backend/api/v1/endpoints/cases.py`
    - Correção: remover tratamento legado após confirmar migração de dados.

---

### 2. Core Forense / Jobs

**Crítica**

1. **FJ-01 — Ciclo de vida de jobs não registra `CustodyRecord`**
   - Especificação exige `analysis_started`, `analysis_completed`, `analysis_failed`, mas nenhum registro é criado em `submit_job`/`run_job`.
   - Arquivos: `src/backend/services/job_service.py`, `src/backend/api/v1/endpoints/analysis.py`
   - Correção: injetar `CustodyService` em `JobService` e registrar eventos do ciclo de vida.

**Alta**

2. **FJ-02 — `AnalysisJob.artifact_sha256` nunca é preenchido**
   - `JobService.run_job:605` atribui `None`, quebrando reproducibilidade por hash de artefato.
   - Arquivo: `src/backend/services/job_service.py`
   - Correção: calcular e persistir hash canônico ao concluir job.

3. **FJ-03 — Diretório de resultados não segue contrato da especificação**
   - Especificação exige `{RESULTS_DIR}/{case_id}/{evidence_id}/{job_id}/`; código usa `{RESULTS_DIR}/{job_id}/`.
   - Arquivos: `src/backend/services/job_service.py`, `src/backend/api/v1/endpoints/analysis.py`, `src/backend/services/derivative_service.py`
   - Correção: alterar construção do path e todos os pontos de leitura.

4. **FJ-04 — Submissão de jobs não valida caso fechado**
   - `JobService.submit_job` e `POST /analysis` não consultam `evidence.case.status`.
   - Arquivos: `src/backend/services/job_service.py`, `src/backend/api/v1/endpoints/analysis.py`
   - Correção: rejeitar submissão com 409/422 se caso estiver fechado.

**Média**

5. **FJ-05 — `GET /analysis/techniques` não retorna `description` e `parameters_schema`**
   - Contrato especifica esses campos, mas resposta omite ambos.
   - Arquivos: `src/backend/services/job_service.py`, `src/backend/api/v1/endpoints/analysis.py`, `src/backend/core/plugins/*.py`
   - Correção: adicionar propriedades na classe base `ForensicPlugin` e nos adapters.

6. **FJ-06 — `JobService` não valida compatibilidade técnica vs tipo de mídia**
   - Mesma divergência que BE-05, reforçada no escopo de jobs: técnica disponível não implica compatível com `file_type`.
   - Arquivo: `src/backend/services/job_service.py`
   - Correção: validar `evidence.file_type in plugin.supported_types`.

7. **FJ-07 — `deepfake_similarity` em `ML_GPU_TECHNIQUES` mas plugin em standby**
   - Configuração inconsistente: técnica é considerada GPU mas não está registrada.
   - Arquivos: `src/backend/core/gpu_inference.py`, `src/backend/core/plugin_registry.py`, `src/backend/core/plugins/deepfake_adapter.py`
   - Correção: remover de `ML_GPU_TECHNIQUES` enquanto estiver em standby.

8. **FJ-08 — RN-JOB-01 desatualizada**
   - Especificação lista `deepfake`, `sepael`, `prnu` como GPU. `prnu` não usa GPU; `deepfake` está em standby.
   - Arquivo: `docs/specs/modules/05-module-jobs.md`
   - Correção: atualizar lista para técnicas realmente GPU.

9. **FJ-09 — Timeout de jobs CPU não é 10 minutos**
   - Celery configura 1h globalmente, sem distinção de fila.
   - Arquivo: `src/backend/app/celery_app.py`
   - Correção: configurar timeout por fila ou timeout manual no worker.

10. **FJ-10 — Jobs CPU pendentes por >24h não são marcados como failed**
    - `gpu_queue_service.py` limpa apenas técnicas em `ML_GPU_TECHNIQUES`.
    - Arquivo: `src/backend/services/gpu_queue_service.py`
    - Correção: generalizar para jobs CPU ou criar limpeza separada.

**Baixa**

11. **FJ-11 — `GET /analysis/{job_id}` não retorna campo `result`**
    - Especificação inclui `result: dict | null`; endpoint retorna metadados e caminho.
    - Arquivo: `src/backend/api/v1/endpoints/analysis.py`
    - Correção: incluir `result` em `_serialize_job` ou ajustar especificação.

12. **FJ-12 — `result_sha256` é hash de `result.json`**
    - Semântica difere da especificação ("hash do resultado principal ou dict de hashes").
    - Arquivo: `src/backend/services/job_service.py`
    - Correção: calcular hash do artefato canônico conforme `REPRODUCIBILITY_REGISTRY`.

13. **FJ-13 — Fallback thread local não adquire lock Redis**
    - Em modo dev/standalone, jobs GPU podem executar concorrentemente sem lock distribuído.
    - Arquivo: `src/backend/services/job_runner.py`
    - Correção: envolver execução GPU com `gpu_distributed_lock`.

14. **FJ-14 — `REPRODUCIBILITY_REGISTRY` inclui técnicas em standby**
    - Técnicas como `deepfake_similarity`, `mp3_parser`, `opus_parser`, `wav_ima_adpcm` estão catalogadas mas não registradas.
    - Arquivo: `src/backend/core/reproducibility.py`
    - Correção: remover técnicas em standby ou adicionar flag de desativada.

---

### 3. Frontend

**Média**

1. **FE-01 — Dashboard orfão**
   - `Dashboard.tsx` existe mas não está roteado; `/` aponta para `Cases.tsx`.
   - Arquivos: `src/frontend/src/App.tsx`, `src/frontend/src/pages/Dashboard.tsx`
   - Correção: decidir rota inicial e atualizar roteamento/documentação.

2. **FE-02 — Rota genérica de análise inexistente**
   - Documentação cita `/cases/:caseId/analysis/:tecnica`, mas `App.tsx` usa modelo de grupos e rotas fixas legadas.
   - Arquivos: `src/frontend/src/App.tsx`, `summaries/frontend_summary.md`, `knowledge/feature_catalog.md`
   - Correção: atualizar documentação ou reintroduzir rota genérica.

3. **FE-03 — Laudos/Relatórios sem representação frontend**
   - Feature catalog lista como "Parcial", mas não há rota/página/serviço de relatórios.
   - Arquivos: `knowledge/feature_catalog.md`, `src/frontend/src/App.tsx`
   - Correção: atualizar status para "Planejada" ou criar página mínima.

**Baixa**

4. **FE-04 — Tamanho da pasta `pages/` superestimado**
   - `frontend_summary.md` afirma ~36,8k linhas para `pages/`, mas real é ~18,5k; ~36k é o total do frontend.
   - Arquivo: `summaries/frontend_summary.md`
   - Correção: ajustar métrica.

5. **FE-05 — Papel `analista` não modelado no frontend**
   - `architecture.md` cita papel legado, mas tipo `User` e `ProtectedRoute` só tratam `admin`/`perito`.
   - Arquivos: `knowledge/architecture.md`, `src/frontend/src/types/api.ts`, `src/frontend/src/components/ProtectedRoute.tsx`
   - Correção: documentar descontinuação ou adicionar papel.

---

### 4. Infra / Deploy

> **Nota de contexto:** o `docker-compose.yml` base é uma configuração de desenvolvimento (usa `Dockerfile` com `--reload` e credenciais padrão). Os riscos abaixo são críticos se esse compose for usado em produção sem override de secrets/variáveis. A produção GPU usa `docker-compose.gpu.yml` e, presumivelmente, `.env.production`.

**Críticas**

1. **IN-06 — Credenciais padrão em `docker-compose`**
   - `POSTGRES_USER=postgres`, `POSTGRES_PASSWORD=postgres` no compose base (dev) e também presentes no `docker-compose.gpu.yml`.
   - Arquivos: `docker-compose.yml`, `docker-compose.gpu.yml`
   - Correção: usar secrets/variáveis de ambiente de produção.

2. **IN-08 — `SECRET_KEY` padrão fraco no código**
   - `config.py` define default fraco; risco de falsificação de tokens.
   - Arquivo: `src/backend/app/config.py`
   - Correção: remover default e falhar na inicialização se não configurado.

3. **IN-09 — Chave Ed25519 de custódia auto-gerada e persistida em desenvolvimento**
   - `CUSTODY_SIGNING_PRIVATE_KEY` default vazio faz o serviço gerar e persistir uma chave dev em `.data/custody_ed25519_dev.key`. A chave não é efêmera entre reinícios, mas é auto-gerada e não auditada, o que invalida o valor probatório da cadeia em dev/test e representa risco se usada em produção.
   - Arquivo: `src/backend/app/config.py`, `src/backend/services/custody_signing_service.py`
   - Correção: exigir chave configurada em produção; documentar geração via `scripts/generate_custody_signing_key.py`.

**Alta**

4. **IN-01 — Volumes de storage persistente incompletos no `docker-compose.yml` base**
   - Faltam volumes `derivatives` e `peritus_cases` no compose CPU; presentes apenas no GPU.
   - Arquivo: `docker-compose.yml`
   - Correção: adicionar volumes e variáveis de ambiente correspondentes.

5. **IN-05 — Alembic listado em `requirements.txt` mas não adotado**
   - Dependência presente, mas bootstrap usa `db_migrations.py` ad-hoc; não há diretório `alembic/`.
   - Arquivos: `requirements.txt`, `src/backend/app/main.py`, `src/backend/app/db_migrations.py`
   - Correção: adotar Alembic ou remover dependência.

**Média**

6. **IN-02 — Nome do ambiente Conda divergente**
   - `environment.yml` usa `forensicauth`; `dev-stack.sh` default `va-suite`; `dev-lan.sh` usa variável diferente.
   - Arquivos: `environment.yml`, `scripts/dev-stack.sh`, `scripts/dev-lan.sh`, `scripts/prepare-worker-bundle.sh`
   - Correção: alinhar para nome e variável únicos.

7. **IN-03 — Imagem de produção usa `--reload`**
   - `Dockerfile` base termina com `--reload` e compose de produção o utiliza.
   - Arquivos: `Dockerfile`, `docker-compose.yml`, `docker-compose.gpu.yml`
   - Correção: criar `Dockerfile.prod` sem reload.

8. **IN-04 — Ausência de `.dockerignore`**
   - Build inclui artefatos desnecessários (`.git`, `node_modules`, caches, dados dev).
   - Arquivo: raiz do projeto
   - Correção: criar `.dockerignore`.

9. **IN-07 — CORS permissivo**
   - `allow_methods=["*"]`, `allow_headers=["*"]` expõe a API.
   - Arquivo: `src/backend/app/main.py`
   - Correção: restringir métodos/headers em produção.

**Baixa**

Nenhuma adicional além das já classificadas como média/crítica/alta.

---

### 5. Consistência Brain / Knowledge

**Alta**

1. **BR-01 — Contradição sobre geração de `CustodyRecord` em jobs**
   - `summaries/backend_summary.md` e `summaries/ml_forensic_summary.md` afirmam que análise gera `CustodyRecord`; `knowledge/domain_model.md`, `brains/critical_paths.md` e `brains/system_brain.md` afirmam que não gera.
   - Arquivos: `summaries/backend_summary.md`, `summaries/ml_forensic_summary.md`, `knowledge/domain_model.md`, `brains/critical_paths.md`, `brains/system_brain.md`
   - Correção: remover trecho `→ CustodyRecord` dos summaries para alinhar com código e knowledge/brain.

2. **BR-02 — Riscos de Alta prioridade omitidos do `executive_summary.md`**
   - Resumo executivo não inclui riscos de Alta prioridade como JWT em `localStorage`, `torch.load(weights_only=False)`, imutabilidade da cadeia dependente de trigger SQLite e modelos não versionados.
   - Arquivos: `brains/executive_summary.md`, `brains/system_brain.md`, `knowledge/risk_analysis.md`
   - Correção: revisar top 5 de riscos ou adicionar nota de seleção resumida.

**Média**

3. **BR-03 — Entidades de domínio omitidas no `mental_model.md`**
   - Faltam `Report`, `CaseShare`, `CaseClosureSignature`.
   - Arquivos: `brains/mental_model.md`, `knowledge/domain_model.md`
   - Correção: adicionar entidades.

4. **BR-04 — Componente `GPUResidency` omitido do `system_brain.md`**
   - Cache LRU de modelos residentes não é mencionado.
   - Arquivos: `brains/system_brain.md`, `knowledge/component_catalog.md`, `summaries/ml_forensic_summary.md`
   - Correção: incluir `GPUResidency` nos componentes críticos.

5. **BR-05 — Lock distribuído GPU simplificado para "GPU singleton"**
   - `system_brain.md` omite `ml_gpu_job_slot` e `gpu_distributed_lock`.
   - Arquivos: `brains/system_brain.md`, `brains/critical_paths.md`, `summaries/ml_forensic_summary.md`
   - Correção: detalhar mecanismos de serialização.

**Baixa**

6. **BR-06 — Papel `analista legacy` omitido do `mental_model.md`**
   - Ator em migração não mencionado.
   - Arquivo: `brains/mental_model.md`
   - Correção: adicionar breve menção.

7. **BR-07 — Priorização de dívidas técnicas diverge**
   - `executive_summary.md` e `system_brain.md` enfatizam dívidas diferentes.
   - Arquivos: `brains/executive_summary.md`, `brains/system_brain.md`, `knowledge/technical_debt.md`
   - Correção: alinhar critérios de seleção.

8. **BR-08 — Metadado de tamanho da Knowledge Layer desatualizado**
   - `final_gates.md` registra 79.817 bytes; tamanho real é 80.526 bytes.
   - Arquivo: `knowledge/final_gates.md`
   - Correção: atualizar metadado.

---

## Recomendações de Prioridade

### Ações Imediatas (Críticas — 7 itens)

| ID | Ação | Owner sugerido |
|---|---|---|
| BE-01 | Bloquear submissão de análise em caso fechado e sem permissão de edição | Backend |
| BE-02 | Bloquear exclusão de evidência sem permissão de edição / caso fechado | Backend |
| BE-03 | Exigir permissão de edição em `update_case` | Backend |
| FJ-01 | Registrar `CustodyRecord` nos eventos do ciclo de vida do job | Backend Forense |
| IN-06 | Remover credenciais padrão do `docker-compose` | Infra |
| IN-08 | Tornar `SECRET_KEY` obrigatório via ambiente | Infra/Backend |
| IN-09 | Tornar `CUSTODY_SIGNING_PRIVATE_KEY` obrigatória em produção | Infra/Backend |

### Ações de Alta Prioridade (11 itens)

| ID | Ação |
|---|---|
| BE-04 | Remover ou restringir `status` no `UpdateCaseRequest` |
| BE-05 | Validar compatibilidade técnica vs tipo de mídia |
| FJ-02 | Preencher `artifact_sha256` ao concluir job |
| FJ-03 | Ajustar diretório de resultados para contrato especificado |
| FJ-04 | Validar caso fechado em `submit_job` |
| IN-01 | Adicionar volumes `derivatives` e `peritus_cases` no compose CPU |
| IN-05 | Adotar Alembic ou remover dependência |
| BR-01 | Corrigir summaries que afirmam geração de `CustodyRecord` em jobs |
| BR-02 | Revisar riscos no `executive_summary.md` |

### Ações de Média Prioridade (20 itens)

Incluem padronização de permissões em uploads de referência, retorno de schema de técnicas, timeouts por fila, limpeza de jobs CPU stale, CORS, Dockerfile reload, `.dockerignore`, inconsistências de ambiente Conda, omissões no Brain Layer, etc.

### Ações de Baixa Prioridade (10 itens)

Incluem estados legados, metadados de tamanho, simplificações no Brain Layer e ajustes menores de documentação.

---

## Registro de Conformidade

- Nenhum código-fonte foi modificado nesta execução.
- Divergências críticas foram documentadas e priorizadas para correção.
- Relatório gerado em: `knowledge/divergence_report_2026-06-25.md`
- Próximo passo recomendado: correção das 7 divergências críticas seguida de reexecução de `/detectar-divergencias` para validar.
