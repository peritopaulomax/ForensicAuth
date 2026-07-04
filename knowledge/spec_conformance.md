# Spec Conformance — ForensicAuth

## Spec

- Nome: ForensicAuth SDD
- Versão: conforme `docs/specs/`
- Status: Parcialmente Conforme

## Cobertura

| Spec | Status | Observação |
|---|---|---|
| 00-overview.md | Conforme | Perfis, histórias, regras de negócio mapeados |
| 01-architecture.md | Conforme | Stack, entidades, endpoints, ADRs implementados |
| 02-module-auth.md | Conforme | JWT, bcrypt, roles |
| 03-module-core.md | Conforme | Plugin registry, ForensicPlugin |
| 04-module-custody.md | Conforme | Cadeia SHA-256 + Ed25519 |
| 04-module-custody-lifecycle.md | Conforme | Compartilhamento, fechamento, assinaturas |
| 05-module-jobs.md | Conforme | Celery, Redis, GPU lock |
| 06-module-image.md | Conforme | Técnicas de imagem plugáveis |
| 07-module-audio.md | Parcialmente Conforme | Parsers MP3/Opus/WAV em standby |
| 08-module-video.md | Parcialmente Conforme | STIL sem peso treinado |
| 09-module-pdf.md | Parcialmente Conforme | pdf_touchup em standby |
| 10-module-reports.md | Em Desenvolvimento | Estrutura existe, mas não detalhada |
| 11-module-case-sharing-lifecycle.md | Conforme | Shares, closure, reopen |
| 12-module-case-transfer.md | Conforme | VCP e Peritus |

## Gaps

| Gap | Impacto | Prioridade |
|---|---|---|
| Testes de regressão forense ausentes | Regra Máxima 8 não validada | Alta |
| Migrations com Alembic adotadas; dev/testes ainda usam create_all | Schema de dev/testes não espelha produção | Média |
| E2E de UI com backend real não existente | Qualidade de frontend | Média |
| deepfake_similarity placeholder | Funcionalidade incompleta | Média |
| STIL sem peso treinado | Técnica indisponível | Média |

## Desvios

| Desvio | Justificativa |
|---|---|
| E2E Python no backend | Scripts Python para testes de ML com pesos reais |
| Dockerfile com reload | Dev-first; produção requer override manual |
| SQLite tolerado | Facilita dev/testes |

## Riscos

- Gaps de conformidade podem comprometer auditabilidade forense.
- Desvios de E2E dificultam cobertura de UI.

## Recomendações

- Implementar testes de regressão forense como prioridade P0.
- Garantir que dev/testes usem Alembic em vez de create_all para validar migrations.
- Finalizar deepfake_similarity ou remover do registro.
- Resolver peso treinado do STIL.

## Score

80/100 (parcialmente conforme, com gaps operacionais e de testes).

## Gate

O sistema implementa a spec funcionalmente, mas possui gaps importantes em testes de regressão forense, migrations e E2E de UI.

## Evidências

- `docs/specs/`
- `tests/specs/`
- `src/backend/core/plugin_registry.py`
- `src/backend/core/plugins/deepfake_adapter.py`
- `src/backend/core/legacy/stil/stil_runtime.py`
