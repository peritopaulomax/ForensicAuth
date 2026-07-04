# Technical Debt — ForensicAuth

## Missão
Mapear fatores que dificultam evolução futura.

## Matriz

| ID | Dívida | Evidência | Impacto | Esforço | Prioridade |
|---|---|---|---|---|---|
| TD-01 | Sem Alembic; migrações ad-hoc em `db_migrations.py` | `src/backend/app/db_migrations.py` | Divergência de schema, deploy frágil | Médio | Alta |
| TD-02 | GPU singleton; apenas um job GPU por vez | `src/backend/core/gpu_inference.py`, `docker-compose.gpu.yml` | Gargalo de throughput | Alto | Alta |
| TD-03 | Frontend com páginas muito grandes (`CaseDetail.tsx` ~1456 linhas) | `src/frontend/src/pages/CaseDetail.tsx` | Manutenibilidade, regressões | Médio | Média |
| TD-04 | Token JWT em `localStorage` | `src/frontend/src/services/api.ts`, `src/frontend/src/store/authStore.ts` | Risco XSS | Médio | Média |
| TD-05 | CORS permissivo (`allow_methods=["*"]`, `allow_headers=["*"]`) | `src/backend/app/main.py` | Segurança | Baixo | Média |
| TD-06 | SECRET_KEY padrão fraco no código | `src/backend/app/config.py` | Tokens forjáveis se `.env` não sobrescrever | Baixo | Média |
| TD-07 | Sem `.dockerignore` confirmado | Build pode enviar arquivos desnecessários | Builds lentos/imagens inchadas | Baixo | Alta |
| TD-07a | Alembic listado em `requirements.txt` mas não adotado operacionalmente | `requirements.txt` | Dependência não utilizada, confusão de migrações | Baixo | Média |
| TD-08 | Dockerfile base com `--reload` | `Dockerfile` | Não adequado para produção pura | Baixo | Média |
| TD-09 | Observabilidade ausente (métricas, tracing, alertas) | - | Dificuldade operacional | Médio | Média |
| TD-10 | Lock de cadeia de custódia local ao processo | `src/backend/services/custody_service.py` | Concorrência em multi-container | Médio | Média |
| TD-11 | Acoplamento de parâmetros por técnica no `JobService` | `src/backend/services/job_service.py` | Complexidade ao adicionar técnicas | Médio | Média |
| TD-12 | Testes de regressão forense não integrados a CI | `scripts/check_*_parity.py` | Qualidade de ML | Alto | Alta |
| TD-13 | Modelos grandes não versionados automaticamente | `models/`, `vendor/` | Rastreabilidade | Médio | Média |
| TD-14 | Código vendorizado sem separação clara de versão/licença | `vendor/` | Auditoria e atualizações | Médio | Média |
| TD-15 | Placeholders de técnicas (`deepfake_similarity`, métodos IMDL ecosystem) | `core/plugins/deepfake_adapter.py`, `core/legacy/imdlbenco/imdlbenco_pipeline.py` | Confusão funcional | Baixo | Média |
| TD-16 | Fallback para CPU em GPU OOM é logado, mas pode passar despercebido na UI | `src/backend/core/gpu_inference.py` | Diagnóstico difícil | Baixo | Média |
| TD-17 | Polling longo no frontend sem WebSocket/retry | `src/frontend/src/hooks/useForensicJob.ts` | UX em jobs longos | Médio | Média |
| TD-18 | `torch.load(weights_only=False)` | Relatório de risco anterior | Segurança de desserialização | Baixo | Alta |
| TD-19 | Scripts de seed removem outros usuários | `scripts/seed_users.py` | Risco operacional | Baixo | Alta |
| TD-20 | Credenciais padrão em docker-compose | `docker-compose.yml` | Risco de deploy inseguro | Baixo | Alta |
| TD-21 | Caso fechado ainda aceita uploads e submissões de jobs | `src/backend/services/evidence_service.py`, `src/backend/services/job_service.py` | Quebra invariante de caso fechado | Baixo | Alta |
| TD-22 | `JobService.submit_job` não valida compatibilidade técnica vs. tipo de mídia | `src/backend/services/job_service.py` | Jobs inválidos podem ser submetidos | Baixo | Alta |
| TD-23 | Ciclo de vida de jobs não gera `CustodyRecord` | `src/backend/services/job_service.py` | Lacuna na cadeia de custódia | Baixo | Alta |
| TD-24 | `PRNUFingerprint` documentado como entidade, mas é `Evidence` derivada | `knowledge/domain_model.md`, `src/backend/services/prnu_fingerprint_service.py` | Modelo de domínio impreciso | Baixo | Média |
| TD-25 | Teste frontend `caseAnalysisNav.test.ts` falha por rota desatualizada | `src/frontend/src/components/__tests__/caseAnalysisNav.test.ts` | Regressão/CI bloqueado | Baixo | Alta |
| TD-26 | Frontend usa fonte Google Fonts externa (viola RNF-01 offline) | `src/frontend/index.html` | Dependência externa | Baixo | Média |
| TD-27 | Nginx frontend sem `client_max_body_size` | `src/frontend/nginx.conf` | Uploads/VCP grandes bloqueados | Baixo | Alta |
| TD-28 | Rotas legadas extensas e fragmentadas no frontend | `src/frontend/src/App.tsx` | Manutenibilidade | Médio | Média |
| TD-29 | Polling longo sem WebSocket/retry robusto | `src/frontend/src/hooks/useForensicJob.ts` | UX em jobs longos | Médio | Média |
| TD-30 | Schemas Pydantic inline nos endpoints | `src/backend/api/v1/endpoints/*.py` | Reutilização e manutenção | Médio | Alta |
| TD-31 | Modelos legados/testados (CLIDE, SAFE, Effort, XGBoost, NPR) ainda presentes no runtime | `models/`, `vendor/`, `src/backend/core/legacy/synthetic_image_detection/` | Limpeza / documentação de legados | Baixo | Média |
| TD-32 | Ausência de score ensemble consolidado | `src/backend/core/plugins/synthetic_image_detection_adapter.py` | UX e interpretação | Médio | Média |
| TD-33 | Thresholds hardcoded (`0.66/0.34`) no ensemble | `src/backend/core/legacy/synthetic_image_detection/pipeline.py` | Calibração por domínio | Médio | Média |
| TD-34 | Ausência de checksums SHA-256 para pesos do ensemble ativo | `models/sepael/`, `models/bfree/`, `models/grip_clipd/` | Integridade forense | Alto | Alta |

## Acoplamento

- `JobService` conhece parâmetros específicos de muitas técnicas
- Frontend `CaseDetail.tsx` concentra múltiplas responsabilidades
- Services dependem entre si sem interfaces explícitas

## Duplicação

- Lógica de validação de acesso em múltiplos endpoints
- Páginas de análise de imagem seguem padrão similar mas duplicam boilerplate

## Complexidade

- `CaseDetail.tsx` (~1456 linhas)
- `job_service.py` (submissão, execução, reprodução, parâmetros específicos)
- `custody_service.py` (encadeamento, selos, verificação, reparo)

## Dependências Frágeis

- `mmcv==1.7.2` legado + IMDL-BenCo
- PyTorch/CUDA compatibilidade
- Links de download de pesos (Google Drive/Dropbox/Baidu)
- `vendor/` sem versionamento explícito

## Arquitetura Degradada

- Migrações ad-hoc em vez de versionadas
- GPU singleton limita escalabilidade
- Storage local compartilhado dificulta multi-réplica

## Testabilidade

- Testes unitários extensivos no backend
- Testes de frontend escassos (~15 arquivos para ~36k linhas)
- Testes de regressão forense manuais

## Observabilidade

- Logs padrão apenas
- Sem métricas estruturadas
- Sem tracing distribuído
- Sem alertas

## Roadmap de Redução

| Ação | Benefício | Prioridade |
|---|---|---|
| Adotar Alembic | Schema versionado | Alta |
| Quebrar `CaseDetail.tsx` em componentes menores | Manutenibilidade | Média |
| Implementar refresh token + httpOnly cookie | Segurança | Média |
| Adicionar `.dockerignore` e remover `--reload` da imagem base | Build/produção | Alta |
| Criar testes de regressão forense automatizados | Qualidade ML | Alta |
| Adicionar métricas e healthchecks | Observabilidade | Média |
| Revisar permissões de upload de referências | Segurança | Média |
| Validar caso fechado em upload/job | Integridade da cadeia | Alta |
| Validar compatibilidade técnica vs. tipo de mídia | Qualidade de jobs | Alta |
| Gerar CustodyRecord no ciclo de vida de jobs | Cadeia de custódia | Alta |
| Adotar ou remover Alembic | Migrações | Média |

## Evidências

- `src/backend/app/db_migrations.py`
- `src/backend/app/main.py`
- `src/backend/app/config.py`
- `src/backend/services/job_service.py`
- `src/backend/services/custody_service.py`
- `src/frontend/src/pages/CaseDetail.tsx`
- `docker-compose.yml`
- `Dockerfile`
