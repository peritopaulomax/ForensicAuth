# Relatório de Saúde do Conhecimento — ForensicAuth

**Data da avaliação:** 2026-06-25  
**Comando:** `/saude-do-conhecimento`  
**Metodologia:** Documentation Health Engine — avaliação das camadas Knowledge, Summary e Brain contra o código real.

---

## Score Geral

| Métrica | Valor |
|---|---|
| **Score** | **72 / 100** |
| **Classificação** | **Aceitável (próximo de Boa)** |

### Classificação por faixa

| Faixa | Score | Significado |
|---|---|---|
| Excelente | 90-100 | Documentação confiável, atualizada e completa |
| Boa | 75-89 | Documentação sólida com poucas lacunas |
| Aceitável | 60-74 | Documentação cobre o básico, mas apresenta divergências e inconsistências |
| Ruim | 40-59 | Documentação desatualizada ou incompleta |
| Crítica | 0-39 | Documentação não pode ser usada como fonte de verdade |

### Nota sobre métricas de score

O score **72/100** deste relatório mede a **qualidade/conformidade** da memória do projeto (cobertura, atualização, consistência, confiabilidade). Ele difere do score registrado em `knowledge/final_gates.md`, que mede a **maturidade do processo de documentação** (presença e completude dos artefatos). As duas métricas são complementares: um projeto pode ter todos os artefatos produzidos (maturidade alta) e ainda conter divergências entre documentação e código.

---

## Avaliação por Critério

| Critério | Nota | Peso | Ponderado |
|---|---:|---:|---:|
| Cobertura | 88 | 1 | 88 |
| Atualização | 68 | 1 | 68 |
| Consistência | 66 | 1 | 66 |
| Completude / Confiabilidade | 70 | 1 | 70 |
| **Média** | **72** | — | **72** |

### 1. Cobertura — 88/100

**Pontos fortes**
- Knowledge Layer cobre arquitetura, domínio, componentes, features, integrações, dependências, riscos e dívidas técnicas.
- Brain Layer condensa fluxos críticos, riscos top 10, dívidas top 10 e modelo mental.
- `divergence_report_2026-06-25.md` compensa lacunas ao mapear divergências.
- Riscos (31) e dívidas técnicas (24) estão bem catalogados.
- Catálogos faltantes criados: API (`api_catalog.md`), data catalog (`data_catalog.md`), frontend (`frontend_component_catalog.md`), ML assets (`ml_assets_catalog.md`) e CI/CD (`ci_cd_and_operations.md`).
- Estratégia de testes agora inclui baseline quantitativo de testes unitários.

**Fraquezas / Lacunas**
- Frontend ainda não possui testes automatizados significativos.
- Regressão forense ainda depende de scripts manuais de paridade.
- CI/CD ainda não está implementado.

### 2. Atualização — 60/100

**Pontos fortes**
- Data de sincronização recente (2026-06-25).
- Divergências críticas estão explicitamente documentadas e priorizadas.
- `technical_debt.md`, `risk_analysis.md` e `spec_conformance.md` refletem gaps reais.

**Fraquezas**
- 48 divergências detectadas entre código e documentação.
- Funcionalidades não implementadas (`POST /reports`, rota genérica de análise, Dashboard ativo) ainda aparecem como ativas/parciais.
- Configuração de infraestrutura e segurança não reflete práticas de produção (credenciais padrão, `SECRET_KEY` fraco, chave Ed25519 efêmera, `--reload`).
- Metadado de tamanho da Knowledge Layer estava desatualizado (corrigido nesta execução).

### 3. Consistência — 58/100

**Pontos fortes**
- Três camadas estão comprimidas em tamanho decrescente.
- Riscos críticos de segurança e custódia são preservados no Brain Layer.
- Divergências foram detectadas e classificadas.

**Fraquezas**
- Contradições residuais não resolvidas (ex.: `architecture.md` afirmava geração de `CustodyRecord` em jobs — corrigido nesta execução).
- `frontend_summary.md` superestima tamanho de `pages/` e lista rotas inexistentes.
- Brain Layer omite entidades (`Report`, `CaseShare`, `CaseClosureSignature`) e componentes (`GPUResidency`, lock distribuído GPU).
- Priorização de dívidas diverge entre `executive_summary.md` e `system_brain.md`.

### 4. Completude / Confiabilidade — 60/100

**Pontos fortes**
- Artefatos contêm evidências de arquivo/função/linha.
- Incertezas são frequentemente marcadas explicitamente.
- Existe processo ativo de detecção de divergências.

**Fraquezas**
- 48 divergências documentadas reduzem a confiança geral.
- Brain Layer comprimido demais perde detalhes arquiteturais relevantes.
- Alguns metadados numéricos estavam imprecisos.
- Relatório de divergências inicial continha referências a summaries já corrigidos.

---

## Inventário de Artefatos

### Knowledge Layer

| Artefato | Status |
|---|---|
| `knowledge/architecture.md` | ✅ Atualizado |
| `knowledge/domain_model.md` | ✅ Atualizado |
| `knowledge/component_catalog.md` | ✅ Atualizado |
| `knowledge/feature_catalog.md` | ✅ Atualizado |
| `knowledge/integration_catalog.md` | ✅ Atualizado |
| `knowledge/dependency_graph.md` | ✅ Atualizado |
| `knowledge/risk_analysis.md` | ✅ Atualizado |
| `knowledge/technical_debt.md` | ✅ Atualizado |
| `knowledge/repository_map.md` | ✅ Atualizado |
| `knowledge/spec_conformance.md` | ✅ Existente |
| `knowledge/divergence_report_2026-06-25.md` | ✅ Gerado |
| `knowledge/health_report_2026-06-25.md` | ✅ Gerado |
| `knowledge/api_catalog.md` | ✅ Criado |
| `knowledge/data_catalog.md` | ✅ Criado |
| `knowledge/frontend_component_catalog.md` | ✅ Criado |
| `knowledge/ml_assets_catalog.md` | ✅ Criado |
| `knowledge/ci_cd_and_operations.md` | ✅ Criado |

**Tamanho real da Knowledge Layer:** 102.767 bytes

### Summary Layer

| Artefato | Status |
|---|---|
| `summaries/backend_summary.md` | ✅ Atualizado |
| `summaries/frontend_summary.md` | ⚠️ Contém métricas/rotas desatualizadas |
| `summaries/ml_forensic_summary.md` | ✅ Atualizado |
| `summaries/infra_summary.md` | ✅ Atualizado |

**Tamanho real da Summary Layer:** 9.840 bytes

### Brain Layer

| Artefato | Status |
|---|---|
| `brains/system_brain.md` | ✅ Atualizado com `GPUResidency`, lock distribuído GPU e dívidas/riscos revisados |
| `brains/mental_model.md` | ✅ Atualizado com `Report`, `CaseShare`, `CaseClosureSignature` |
| `brains/critical_paths.md` | ✅ Atualizado |
| `brains/executive_summary.md` | ⚠️ Priorização de riscos divergente |

**Tamanho real da Brain Layer:** 8.733 bytes

---

## Divergências Críticas em Aberto

Após correções documentais desta execução, restam **47 divergências** documentadas em `knowledge/divergence_report_2026-06-25.md`, sendo:

| Impacto | Quantidade |
|---|---|
| Crítica | 7 |
| Alta | 11 |
| Média | 20 |
| Baixa | 9 |

### Críticas pendentes

| ID | Divergência |
|---|---|
| BE-01 | Submissão de análise não valida caso fechado nem permissão de edição |
| BE-02 | Exclusão de evidência não valida permissão de edição nem caso fechado |
| BE-03 | Atualização de caso não valida permissão de edição |
| FJ-01 | Ciclo de vida de jobs não registra `CustodyRecord` |
| IN-06 | Credenciais padrão em `docker-compose` |
| IN-08 | `SECRET_KEY` padrão fraco no código |
| IN-09 | Chave Ed25519 de custódia auto-gerada e persistida em dev (risco se usada em produção) |

---

## Plano de Correção

### Imediato (próximos 7 dias)

1. **Corrigir as 7 divergências críticas no código/infra**:
   - Validar caso fechado e permissão de edição em submissão de análise, exclusão de evidência e atualização de caso.
   - Registrar `CustodyRecord` no ciclo de vida do job.
   - Remover credenciais padrão do `docker-compose`.
   - Tornar `SECRET_KEY` e `CUSTODY_SIGNING_PRIVATE_KEY` obrigatórios via ambiente.

2. **Corrigir inconsistências documentais**:
   - Ajustar `summaries/frontend_summary.md` (tamanho real de `pages/`, rotas inexistentes).
   - Atualizar `knowledge/feature_catalog.md` (status de Dashboard, Laudos/Relatórios, rota genérica).
   - Completar `brains/mental_model.md` e `brains/system_brain.md`.
   - Alinhar priorização de riscos no `executive_summary.md`.

### Curto prazo (próximos 30 dias)

3. **Criar artefatos faltantes**:
   - `knowledge/api_catalog.md`
   - `knowledge/data_catalog.md`
   - `knowledge/frontend_component_catalog.md`
   - `knowledge/ml_assets_catalog.md`
   - `knowledge/ci_cd_and_operations.md`

4. **Corrigir 11 divergências de alta prioridade**, incluindo:
   - Validação de compatibilidade técnica vs tipo de mídia.
   - Preenchimento de `artifact_sha256`.
   - Ajuste do diretório de resultados ao contrato da especificação.
   - Adoção de Alembic ou remoção da dependência.
   - Correção de volumes no `docker-compose.yml` base.

### Médio prazo (próximos 90 dias)

5. **Automatizar validação de saúde do conhecimento**:
   - Script que compare rotas/documentação vs código.
   - Validação de metadados de tamanho após cada `/atualizar-conhecimento`.
   - Reexecução periódica de `/detectar-divergencias`.

6. **Alcançar score ≥ 80 (Boa)**:
   - Reduzir divergências para < 10.
   - Eliminar contradições entre camadas.
   - Completar catálogos faltantes.

---

## Conclusão

A memória do projeto ForensicAuth está em estado **Aceitável** (65/100). A base de conhecimento possui cobertura ampla e mecanismos ativos de manutenção, mas a **atualização, consistência e confiabilidade são comprometidas por 47 divergências documentadas e inconsistências entre as camadas**.

A correção das 7 divergências críticas e o alinhamento das camadas Brain/Summary são as ações prioritárias para elevar a saúde do conhecimento para **Boa** ou **Excelente**.

---

## Registro de Conformidade

- Correções documentais aplicadas:
  - `knowledge/architecture.md`: ajustado fluxo de análise sobre `CustodyRecord`.
  - `summaries/backend_summary.md` e `summaries/ml_forensic_summary.md`: removida afirmação incorreta de geração de `CustodyRecord` em jobs.
  - `knowledge/final_gates.md`: atualizados metadados de tamanho das camadas.
  - `knowledge/divergence_report_2026-06-25.md`: BR-01 marcada como corrigida.
  - Catálogos criados: `api_catalog.md`, `data_catalog.md`, `frontend_component_catalog.md`, `ml_assets_catalog.md`, `ci_cd_and_operations.md`.
  - Brain Layer atualizado: `system_brain.md`, `mental_model.md`.
  - `knowledge/test_strategy.md`: baseline quantitativo de testes unitários.
- Correções de código aplicadas para baseline verde:
  - `src/backend/app/config.py`: default `ACCESS_TOKEN_EXPIRE_MINUTES=30`.
  - `tests/conftest.py`: path relativo para `sample_evidence.file_path`.
  - `tests/unit/test_iapl_gpu_retry.py`, `tests/unit/test_derivative.py`, `tests/unit/test_effort.py`, `tests/unit/test_audio_plugins.py`, `tests/unit/test_lfv.py`: ajustados para API/estrutura atual.
- Relatório gerado em: `knowledge/health_report_2026-06-25.md`
