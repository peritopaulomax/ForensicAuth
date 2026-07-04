# Relatório de Divergências — ForensicAuth

**Data da detecção:** 2026-06-29  
**Comando:** `/analisar-repositorio-multiagente`  
**Metodologia:** Multi-Agent Orchestration + Repository Intelligence — comparação entre Código, Knowledge Layer, Summary Layer, Brain Layer e Specs.

---

## Resumo Executivo

Foram detectadas **15 divergências novas ou reconfirmadas** entre a base de conhecimento e o código/infraestrutura atual do projeto ForensicAuth, após análise multiagente.

| Categoria | Quantidade |
|---|---|
| Crítica | 4 |
| Alta | 5 |
| Média | 4 |
| Baixa | 2 |
| **Total** | **15** |

### Distribuição por Escopo

| Escopo | Crítica | Alta | Média | Baixa | Total |
|---|---:|---:|---:|---:|---:|
| Domínio / Requisitos | 2 | 1 | 1 | 0 | 4 |
| ML / Forense | 1 | 2 | 1 | 0 | 4 |
| Frontend | 0 | 1 | 1 | 1 | 3 |
| Infra / Deploy | 1 | 1 | 1 | 1 | 4 |

---

## Matriz Consolidada de Divergências

| ID | Escopo | Divergência | Impacto | Status |
|---|---|---|---|---|
| D-01 | Domínio | Role `analista` especificada em `00-overview.md` mas removida do código (migração para `perito`) | Crítica | Documentado |
| D-02 | Domínio | Módulo de laudos/relatórios (Reports) especificado mas não implementado no backend | Crítica | Documentado |
| D-03 | Domínio | Imutabilidade de `custody_records` só é garantida por trigger SQLite; PostgreSQL não possui mecanismo equivalente | Crítica | Documentado |
| D-04 | Domínio | `Evidence.file_type` inclui `"documento"` além dos 4 tipos da especificação | Baixa | Documentado |
| D-05 | ML/Forense | `torch.load(weights_only=False)` em ~22 pipelines legados | Crítica | Documentado |
| D-06 | ML/Forense | Técnicas em `STANDBY_PLUGIN_NAMES` (mp3_parser, opus_parser, pdf_touchup, deepfake_similarity) não registradas ativamente | Alta | Documentado |
| D-07 | ML/Forense | Métodos IMDL-BenCo `ecosystem` visíveis mas requerem pesos/vendors adicionais | Alta | Documentado |
| D-08 | ML/Forense | Modelos testados no passado (CLIDE, SAFE, Effort, XGBoost, NPR) ainda presentes mas não fazem parte do ensemble `synthetic_image_detection` ativo | Baixa | Documentado |
| D-09 | Frontend | Teste `caseAnalysisNav.test.ts` falha por rota desatualizada | Alta | Documentado |
| D-10 | Frontend | Fonte Google Fonts externa carregada no `index.html` (viola RNF-01 offline) | Média | Documentado |
| D-11 | Frontend | Roteamento fragmentado: rotas legadas por técnica coexistem com hubs modernos | Baixa | Documentado |
| D-12 | Infra | Credenciais padrão (`POSTGRES_USER/PASSWORD=postgres`) ainda presentes em docker-compose | Crítica | Documentado |
| D-13 | Infra | Dockerfile base usa `--reload` e é utilizado em compose de "produção" | Alta | Documentado |
| D-14 | Infra | Nginx frontend não define `client_max_body_size` | Média | Documentado |
| D-15 | Infra | Ambiente conda divergente (`forensicauth` no `environment.yml` vs `va-suite` no `dev-stack.sh`) | Baixa | Documentado |

---

## Detalhamento por Escopo

### 1. Domínio / Requisitos

**Críticas**

1. **D-01 — Role `analista` especificada mas removida do código**
   - `docs/specs/00-overview.md` descreve papel `Analista` com visualização restrita; `models/user.py` enum só tem `admin`/`perito`; `db_migrations.py:ensure_migrate_analista_to_perito` migra analistas existentes.
   - Arquivos: `docs/specs/00-overview.md`, `src/backend/models/user.py`, `src/backend/app/db_migrations.py`
   - Correção: decidir se reintroduz `analista` com permissões read-only ou atualiza a especificação.

2. **D-02 — Módulo de laudos/relatórios não implementado no backend**
   - Modelo `Report` existe em `src/backend/models/report.py`, mas não há `ReportService`, Celery task `generate_report` nem router `/reports` registrado em `app/main.py`.
   - Arquivos: `src/backend/models/report.py`, `src/backend/app/main.py`, `docs/specs/modules/10-module-reports.md`
   - Correção: implementar service, task e endpoints OU atualizar especificação/status para "não implementado".

3. **D-03 — Imutabilidade da cadeia dependente de trigger SQLite**
   - `app/database.py` cria trigger SQLite `trg_custody_immutable`; comentário indica que PostgreSQL dependerá de GRANT/REVOKE/policy, mas não há implementação.
   - Arquivos: `src/backend/app/database.py`, `src/backend/models/custody_record.py`
   - Correção: implementar trigger/policy/RLS equivalente em PostgreSQL.

**Alta**

4. **D-? — Schemas Pydantic inline nos endpoints (reconfirmado)**
   - Não há diretório `src/backend/schemas/`; modelos Pydantic estão definidos dentro dos endpoints.
   - Arquivos: `src/backend/api/v1/endpoints/*.py`
   - Correção: centralizar schemas reutilizáveis.

**Baixa**

5. **D-04 — Tipo `"documento"` além dos 4 tipos da spec**
   - `models/evidence.py` enum inclui `"documento"`; `docs/specs/01-architecture.md` lista apenas imagem, áudio, vídeo, PDF.
   - Arquivos: `src/backend/models/evidence.py`, `docs/specs/01-architecture.md`
   - Correção: alinhar modelo e especificação.

---

### 2. ML / Forense

**Crítica**

6. **D-05 — `torch.load(weights_only=False)` em ~22 pipelines legados**
   - Pipelines em `src/backend/core/legacy/*` carregam pesos PyTorch sem `weights_only=True`, permitindo execução de código arbitrário.
   - Arquivos: `src/backend/core/legacy/*/*pipeline*.py`, `src/backend/core/legacy/*/*runtime*.py`
   - Correção: migrar para `weights_only=True` ou usar `safetensors`; exigir teste de equivalência (Regra Máxima 8).

**Alta**

7. **D-06 — Técnicas em standby não registradas**
   - `plugin_registry.py` define `STANDBY_PLUGIN_NAMES` com `mp3_parser`, `opus_parser`, `pdf_touchup`, `deepfake_similarity`, etc. Essas técnicas aparecem em specs mas não estão disponíveis para execução.
   - Arquivos: `src/backend/core/plugin_registry.py`, `docs/specs/modules/07-module-image.md`, `docs/specs/modules/09-module-pdf.md`
   - Correção: ativar ou remover do registry e atualizar specs.

8. **D-07 — Métodos IMDL-BenCo ecosystem sem pesos/vendors**
   - IMDL-BenCo hub expõe métodos nativos + ecosystem; métodos ecosystem dependem de vendors/pesos adicionais nem sempre presentes.
   - Arquivos: `src/backend/core/legacy/imdlbenco/imdlbenco_catalog.py`, `vendor/`
   - Correção: documentar checklist de downloads e validar disponibilidade no warmup.

**Média**

9. **D-08 — Worker GPU não incluído no docker-compose base**
   - `docker-compose.yml` CPU não inclui worker GPU; produção GPU requer `docker-compose.gpu.yml` separado.
   - Arquivos: `docker-compose.yml`, `docker-compose.gpu.yml`
   - Correção: documentar claramente que análises GPU exigem compose GPU.

---

### 3. Frontend

**Alta**

10. **D-09 — Teste `caseAnalysisNav.test.ts` quebrado**
    - Vitest reporta 1 falha em `caseAnalysisNav.test.ts` devido a rota desatualizada.
    - Arquivos: `src/frontend/src/components/__tests__/caseAnalysisNav.test.ts`, `src/frontend/src/App.tsx`
    - Correção: atualizar teste ou rota.

**Média**

11. **D-10 — Fonte Google Fonts externa**
    - `src/frontend/index.html` carrega fonte do Google, violando RNF-01 (offline).
    - Arquivo: `src/frontend/index.html`
    - Correção: embutir fonte localmente.

**Baixa**

12. **D-11 — Roteamento fragmentado**
    - Coexistem rotas legadas por técnica (`/cases/:id/analysis/ela`) e hubs modernos (`/image-group/:groupId`).
    - Arquivo: `src/frontend/src/App.tsx`
    - Correção: consolidar roteamento.

---

### 4. Infra / Deploy

**Crítica**

13. **D-12 — Credenciais padrão em docker-compose**
    - `docker-compose.yml` e `docker-compose.gpu.yml` definem `POSTGRES_USER=postgres`, `POSTGRES_PASSWORD=postgres`.
    - Arquivos: `docker-compose.yml`, `docker-compose.gpu.yml`
    - Correção: usar secrets/variáveis de ambiente e falhar se não configuradas.

**Alta**

14. **D-13 — Dockerfile base usa `--reload` em produção**
    - `Dockerfile` termina com `--reload` e é usado por `docker-compose.yml`.
    - Arquivos: `Dockerfile`, `docker-compose.yml`
    - Correção: criar `Dockerfile.prod` sem reload e usá-lo no compose de produção.

**Média**

15. **D-14 — Nginx sem `client_max_body_size`**
    - `src/frontend/nginx.conf` não define limite de upload; uploads/VCP grandes podem ser bloqueados.
    - Arquivo: `src/frontend/nginx.conf`
    - Correção: configurar `client_max_body_size` adequado (ex: 600M).

**Baixa**

16. **D-15 — Nome do ambiente conda divergente**
    - `environment.yml` usa `forensicauth`; `scripts/dev-stack.sh` default `va-suite`.
    - Arquivos: `environment.yml`, `scripts/dev-stack.sh`
    - Correção: alinhar nome/variável.

---

## Recomendações de Prioridade

### Ações Imediatas (Críticas)

| ID | Ação | Owner sugerido |
|---|---|---|
| D-05 | Migrar `torch.load` para `weights_only=True` com teste de equivalência | ML/Forense |
| D-12 | Remover credenciais padrão dos docker-compose | Infra |
| D-02 | Implementar módulo de laudos ou atualizar specs | Backend |
| D-03 | Garantir imutabilidade da cadeia em PostgreSQL | Backend/DBA |

### Ações de Alta Prioridade

| ID | Ação |
|---|---|
| D-06 | Ativar ou remover técnicas em standby |
| D-07 | Documentar checklist de pesos do IMDL-BenCo ecosystem |
| D-09 | Corrigir teste frontend quebrado |
| D-13 | Criar Dockerfile de produção sem reload |
| D-? | Centralizar schemas Pydantic |

### Ações de Média/Baixa Prioridade

- D-01: Resolver papel `analista`
- D-04: Alinhar tipo `"documento"` com spec
- D-08: Documentar necessidade de compose GPU
- D-10: Embutir fonte localmente
- D-11: Consolidar rotas legadas
- D-14: Configurar `client_max_body_size`
- D-15: Alinhar nome do ambiente conda

---

## Registro de Conformidade

- Nenhum código-fonte foi modificado nesta execução.
- Divergências críticas foram documentadas e priorizadas para correção.
- Relatório gerado em: `knowledge/divergence_report_2026-06-29.md`
- Próximo passo recomendado: correção das 4 divergências críticas seguida de reexecução de `/detectar-divergencias` para validar.
