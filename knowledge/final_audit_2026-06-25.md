# Final Audit — Self Reflection / Revisão de Análise

**Data:** 2026-06-25  
**Objetivo:** Revisar criticamente as análises anteriores da documentação e do código para identificar hipóteses, lacunas, excesso de confiança e explicações alternativas.

---

## Fatos Consolidados

1. O repositório ForensicAuth estava em desenvolvimento ativo no momento da análise; o working tree continha modificações não commitadas.
2. Foram detectadas **48 divergências** entre código/infra e a base de conhecimento (`knowledge/divergence_report_2026-06-25.md`).
3. A Health Report calculou **score 65/100 (Aceitável)**, enquanto `final_gates.md` registrava **score 85/100** de maturity de Repository Intelligence.
4. Divergências críticas têm evidências de código fortes:
   - Submissão de análise (`POST /analysis`) não valida caso fechado nem permissão de edição.
   - Exclusão de evidência não valida permissão de edição nem caso fechado.
   - Atualização de caso (`PUT /cases/{id}`) não valida permissão de edição.
   - Ciclo de vida de jobs não chama `CustodyService`.
   - `SECRET_KEY` e `CUSTODY_SIGNING_PRIVATE_KEY` possuem defaults inseguros em `config.py`.
   - `docker-compose.yml` base contém credenciais default `postgres/postgres`.
5. O upload principal de evidências **já valida** caso fechado via `_require_case_mutable`; a divergência está em submissão de análise e uploads de referência técnica.
6. A chave Ed25519 em dev **não é efêmera** — é gerada automaticamente e **persistida** em `.data/custody_ed25519_dev.key`.
7. O `Dockerfile` base usa `--reload` e o `docker-compose.yml` base é claramente **configuração de desenvolvimento**, não produção.
8. `artifact_sha256` é atribuído `None` em `run_job`; `result_sha256` é hash de `result.json`.
9. `frontend_summary.md` superestimou o tamanho da pasta `pages/` (~36,8k vs ~18,5k reais).
10. Catálogos de APIs, dados, frontend components, ML assets e CI/CD foram criados posteriormente; ainda é necessário mantê-los sincronizados com o código.

---

## Hipóteses Identificadas

| ID | Hipótese | Confiança | Como Validar |
|---|---|---|---|
| H-01 | Jobs não geram `CustodyRecord` por decisão de design (preview exploratório). | Média | Consultar `docs/specs/modules/04-module-custody.md` RN-CUST-03 vs `05-module-jobs.md`; perguntar a stakeholders. |
| H-02 | `artifact_sha256 = None` é intencional porque não há artefato único para todas as técnicas. | Média | Documentar semântica de `artifact_sha256` vs `result_sha256`; verificar `REPRODUCIBILITY_REGISTRY`. |
| H-03 | `docker-compose.yml` base é dev-only; produção usa outro compose ou `.env.production`. | Média | Verificar `.env.production.example` e processo de deploy real. |
| H-04 | `deepfake_similarity` em `ML_GPU_TECHNIQUES` é configuração forward-compatible. | Média | Confirmar intenção no código ou na spec; verificar comentários/histórico. |
| H-05 | Dashboard e rota genérica de análise são reservas/UX deliberadas. | Média | Consultar decisões de design ou histórico de commits. |
| H-06 | A imutabilidade da cadeia de custódia é garantida apenas em SQLite (trigger), não em PostgreSQL. | Baixa/Média | Inspecionar banco de produção/dev por triggers/RLS/GRANT em `custody_records`. |
| H-07 | Score 85/100 em `final_gates.md` mede maturity de artefatos; 65/100 do health report mede qualidade/conformidade. | Média | Documentar diferença explícita entre as métricas. |

---

## Incertezas

1. **Intenção de design por trás de 48 divergências:** não foi confirmado quais são bugs, débito planejado, escolhas de UX ou configurações de ambiente.
2. **Estado real de deploy em produção:** não foi possível inspecionar `.env.production.example` (sensível) nem confirmar se CI/CD/override de secrets existem.
3. **Execução da suíte de testes:** baseline de testes unitários foi estabelecida (461 passados, 0 falhas); testes de integração e frontend ainda precisam de cobertura.
4. **Migração de papel `analista`:** não está claro se ainda existem usuários `analista` ativos ou se a migração foi concluída.
5. **Readiness de técnicas em standby:** não há matriz de quais técnicas estão realmente funcionais, com pesos e testes.
6. **Comportamento de concorrência GPU em fallback thread-local:** não foi testado se dois jobs GPU podem executar simultaneamente sem lock distribuído.
7. **Impacto real do `docker-compose.yml` CPU sem volumes `derivatives`/`peritus_cases`.**

---

## Lacunas

| Área | Lacuna | Impacto |
|---|---|---|
| APIs | Não há `api_catalog.md` com contratos completos | Médio |
| Dados | Não há `data_catalog.md` com schema do banco | Médio |
| Frontend | Não há catálogo de componentes/páginas | Médio |
| ML Assets | Não há catálogo de modelos/pesos | Alto |
| CI/CD | Não há documentação de deploy/ops | Alto |
| Testes | Baseline unitária criada; integração e frontend pendentes | Médio |
| Transferências | Fluxos de `case_transfer` e `peritus_transfer` não foram detalhados | Médio |
| Scheduler | `preview_cleanup_scheduler` não aparece em nenhum catálogo | Baixo/Médio |
| Reproducibilidade | Não há evidência de execução dos scripts `check_*_parity.py` | Médio |

---

## Riscos de Interpretação

1. **Score 65/100 como "Aceitável"** pode ser excessivamente otimista para um sistema com 7 divergências críticas de segurança/custódia. A rubrica não é transparente.
2. **Classificar todas as divergências como bugs** pode levar a correções desnecessárias ou contraditórias com decisões de design.
3. **Chave Ed25519 descrita como "efêmera"** exagera o risco real (é persistida) e pode direcionar mitigação errada.
4. **`docker-compose.yml` base tratado como produção** distorce a priorização de riscos de infraestrutura.
5. **Confiança "Alta" em `architecture.md`** é inconsistente com 48 divergências documentadas.
6. **Imutabilidade da cadeia assumida como invariante** pode não valer em PostgreSQL sem triggers/RLS.
7. **Working tree dirty (151 arquivos)** invalida parcialmente a comparação contra baseline estável.

---

## Explicações Alternativas Relevantes

| Conclusão Original | Explicação Alternativa | Impacto na Priorização |
|---|---|---|
| FJ-01: jobs não geram CustodyRecord = bug crítico | Decisão de design: jobs são previews; custódia formal entra em upload/derivado/fechamento. | Pode reduzir prioridade se confirmado. |
| FJ-02: `artifact_sha256 = None` = bug | Semântica intencional: `result_sha256` já captura manifesto determinístico. | Requer documentação, não necessariamente correção. |
| IN-06/IN-08/IN-09: defaults inseguros = crítico | Defaults dev-only; produção real pode sobrescrever. | Continua alto até confirmado, mas mitigação é documentação/validação, não apenas correção de código. |
| IN-03: Dockerfile com reload = produção | Dockerfile base é dev; falta `Dockerfile.prod`. | Dívida técnica, não bug de segurança crítico. |
| FE-01/FE-02: Dashboard/rota genérica = divergência | Escolha de UX deliberada; Dashboard é reserva futura. | Baixa prioridade técnica. |
| FJ-12: `result_sha256` de JSON = semântica errada | `result.json` pode ser artefato canônico intencional. | Requer alinhamento de spec. |

---

## Correções Documentais Aplicadas

Após a revisão, foram aplicadas as seguintes correções nos artefatos de conhecimento:

1. **`knowledge/divergence_report_2026-06-25.md`**:
   - BE-01: ajustada descrição para esclarecer que upload principal já valida caso fechado; a divergência está em submissão de análise e uploads de referência técnica.
   - IN-09: corrigida terminologia de "chave efêmera" para "chave dev auto-gerada e persistida".
   - Adicionada nota de contexto sobre `docker-compose.yml` base ser configuração de desenvolvimento.

2. **`knowledge/health_report_2026-06-25.md`**:
   - Ajustada descrição do risco Ed25519 para refletir persistência da chave dev.
   - Adicionada seção explicando diferença entre maturity score e health score.

3. **`knowledge/final_gates.md`**:
   - Adicionada nota sobre os dois scores (85 maturity vs 65 health) e suas dimensões distintas.

---

## Confiança Global da Análise Revisada

| Dimensão | Confiança | Justificativa |
|---|---|---|
| Divergências críticas mapeadas | **Alta** | Evidências de arquivo/linha e verificáveis no código |
| Classificações de impacto | **Média** | Subjetivas, mas razoáveis; dependem de confirmação de design |
| Score de saúde (65/100) | **Média** | Metodologia deve ser tornada transparente; pode subestimar severidade |
| Confiança geral em arquitetura | **Média** | Excesso de otimismo diante de 48 divergências |
| Invariantes de domínio | **Baixa/Média** | Dependem de implementação/configuração não confirmada |
| Intencionalidade de "bugs" | **Média** | Existem explicações plausíveis de design evolutivo |
| Completude da análise | **Média** | Faltam catálogos e baseline de testes/deploy |

**Confiança Global: Média**

---

## Recomendações para Reduzir Incerteza

1. **Estabilizar o working tree** (commit das modificações pendentes) antes de reexecutar análises automatizadas.
2. **Manter a baseline de testes** atualizada e expandir para integração e frontend (`pytest --cov`, `vitest --coverage`).
3. **Inspecionar ambiente de produção/dev real:** `.env.production`, triggers/RLS no PostgreSQL, processo de deploy.
4. **Resolver contradições normativas:** alinhar `04-module-custody.md` RN-CUST-03 com `05-module-jobs.md` sobre `CustodyRecord` em jobs.
5. **Documentar decisões arquiteturais** para casos ambíguos (jobs/custódia, `artifact_sha256`, `deepfake_similarity`, Dashboard).
6. **Criar catálogos faltantes:** API, dados, frontend, ML assets, CI/CD.
7. **Tornar a rubrica do health score transparente** ou unificar métrica com `final_gates.md`.
8. **Reexecutar `/detectar-divergencias` e `/saude-do-conhecimento`** após correções para validar.

---

## Conclusão

A análise original é abrangente e útil, mas apresenta **excesso de confiança em algumas interpretações** e **imprecisões terminológicas**. Várias das 48 divergências podem refletir decisões de design, placeholders planejados ou configurações dev-first, não apenas bugs. A principal recomendação é **validar intenções de design antes de priorizar correções de código**, estabilizar o working tree e completar os catálogos operacionais faltantes.
