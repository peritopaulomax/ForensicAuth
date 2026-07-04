# Test Strategy — ForensicAuth

## Missão
Transformar arquitetura em estratégia de testes.

## Cobertura

### Unitários
- Backend: testes em `tests/unit/` cobrem auth, casos, evidências, jobs, custódia, lifecycle, integridade, derivados
- Frontend: testes em `src/frontend/src/**/*.test.ts*` (escassos, ~15 arquivos)

### Integração
- `tests/integration/` (escopo não detalhado nos relatórios)
- Testes de API com `httpx`/`TestClient`

### Contrato
- Schemas Pydantic inline nos endpoints
- Tipos TypeScript no frontend (`src/frontend/src/types/api.ts`)

### E2E
- Frontend: Playwright (`src/frontend/e2e/`)
- E2E Python: `tests/e2e/` (se existir)

### Performance
- Benchmarks de técnicas forenses em `scripts/bench_*.py`
- Não há testes de carga da API

### Segurança
- JWT tests
- RBAC tests
- Não há scan de dependências ou pentest automatizado

### IA
- Scripts de paridade (`scripts/check_*_parity.py`) validam equivalência com vendors
- Não integrados a CI
- Dependem de pesos de modelos

## Matriz de Testes

| Componente | Tipo de Teste | Prioridade |
|---|---|---|
| AuthService | Unitário | Alta |
| CaseLifecycleService | Unitário | Alta |
| EvidenceService | Unitário | Alta |
| JobService | Unitário/Integração | Alta |
| CustodyService | Unitário | Alta |
| CustodySigningService | Unitário | Alta |
| ForensicIntegrityService | Unitário | Alta |
| PluginRegistry | Unitário | Média |
| GPUInference | Integração | Média |
| Reproducibility | Unitário | Alta |
| Frontend pages | Componente/E2E | Média |
| API endpoints | Integração | Alta |
| Regressão forense | Paridade/CI | Alta |

## Críticos

### Fluxos críticos
1. Login → JWT
2. Criar caso → upload evidência → cadeia de custódia
3. Submeter análise → job → resultado → cadeia
4. Salvar derivado → provenance
5. Fechar caso → assinaturas
6. Verificar integridade forense

### Integrações críticas
- PostgreSQL
- Redis
- Filesystem
- Celery workers

### Dados críticos
- CustodyRecord
- Evidence
- AnalysisJob
- CaseClosure

## Lacunas

| Lacuna | Impacto | Prioridade |
|---|---|---|
| Poucos testes frontend | Regressões de UI | Alta |
| Sem CI/CD | Qualidade inconsistente | Alta |
| Testes de regressão forense não automatizados | Qualidade de ML | Alta |
| Sem testes de carga | Escalabilidade desconhecida | Média |
| Sem testes de segurança automatizados | Vulnerabilidades | Média |
| Sem testes de disponibilidade | Resiliência | Média |

## Riscos

| Risco | Impacto |
|---|---|
| Cobertura frontend baixa | Regressões visuais/funcionais |
| Ausência de CI | Deploy com defeitos |
| Testes ML dependentes de pesos | Execução lenta/flaky |
| Mock de GPU difícil | Testes GPU limitados |

## Roadmap

| Ação | Benefício | Prioridade |
|---|---|---|
| Criar CI/CD (GitHub Actions/GitLab CI) | Qualidade contínua | Alta |
| Aumentar cobertura frontend | Menos regressões | Alta |
| Automatizar testes de paridade forense | Qualidade ML | Alta |
| Adicionar testes de carga da API | Confiabilidade | Média |
| Adicionar scan de dependências | Segurança | Média |
| Testes de contrato API ↔ frontend | Integridade | Média |

## Baseline de Testes Unitários (2026-06-25)

Executados em lotes via `scripts/run_test_baseline.py` (processo único trava por acúmulo de GPU/threads):

| Métrica | Valor |
|---|---|
| Passados | 461 |
| Falhas | 0 |
| Skipped | 5 |
| Erros | 0 |

Batches:
1. Core/custódia/evidências/jobs — 159 passados
2. JPEG/metadata/fases/frontend — 197 passados, 4 skipped
3. Runtime camo/clide/deeclip/distildire/effort — 19 passados
4. GPU residency/IAPL/IMDL — 29 passados
5. Noiseprint/copy-move/LFV/PDF — 57 passados, 1 skipped

Relatório gerado: `tests/unit_baseline_report.json`
Script: `scripts/run_test_baseline.py`

### Correções aplicadas para baseline verde
- `src/backend/app/config.py`: `ACCESS_TOKEN_EXPIRE_MINUTES` default 30 (alinha com TU-CORE-005)
- `tests/conftest.py`: `sample_evidence.file_path` relativo (`./uploads/teste.jpg`) para evitar permissão negada
- `tests/unit/test_iapl_gpu_retry.py`: monkeypatch de `prepare_vram_for_iapl_if_needed` (API atual)
- `tests/unit/test_derivative.py`: uso de `build_job_result_dir` para estrutura aninhada de resultados
- `tests/unit/test_effort.py`: passar `variants` explícito no teste de warmup
- `tests/unit/test_audio_plugins.py`: assert ajustado para 5 plugins de áudio ativos (mp3/opus/wav em standby)
- `tests/unit/test_lfv.py`: isolamento de vendor verificado via subprocesso limpo

## Gate

O que ainda não está protegido: frontend em geral, regressão forense, carga, segurança automatizada.

## Evidências

- `tests/`
- `tests/unit_baseline_report.json`
- `scripts/run_test_baseline.py`
- `src/frontend/e2e/`
- `src/frontend/src/**/*.test.ts*`
- `scripts/check_*_parity.py`
- `scripts/bench_*.py`
