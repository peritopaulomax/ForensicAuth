# Risk Analysis — ForensicAuth

## Missão
Mapear riscos reais do sistema.

## Matriz

| ID | Categoria | Risco | Impacto | Probabilidade | Prioridade | Mitigação |
|---|---|---|---|---|---|---|
| R-01 | Segurança | SECRET_KEY padrão fraco no código | Alto | Média | Alta | Sobrescrever em `.env` de produção |
| R-02 | Segurança | Token JWT em `localStorage` (XSS) | Alto | Média | Alta | Migrar para httpOnly cookie + refresh token |
| R-03 | Segurança | CORS permissivo | Médio | Média | Média | Restringir origins em produção |
| R-04 | Segurança | Upload de referências sem exigir permissão de edição | Médio | Média | Média | Validar `_require_case_mutable` |
| R-05 | Segurança | `torch.load(weights_only=False)` | Alto | Baixa | Alta | Usar `weights_only=True` quando possível |
| R-06 | Disponibilidade | PostgreSQL único (sem replicação) | Alto | Baixa | Alta | Backup diário + replicação futura |
| R-07 | Disponibilidade | Redis único (broker + backend + lock) | Alto | Baixa | Alta | Redis Sentinel ou backup |
| R-08 | Disponibilidade | Storage local compartilhado sem replicação | Alto | Baixa | Alta | Backup para OneDrive corporativo |
| R-09 | Disponibilidade | Worker GPU único | Médio | Média | Média | Adicionar workers GPU, suporte a múltiplas GPUs |
| R-10 | Escalabilidade | GPU singleton (um job por vez) | Médio | Alta | Alta | Fila por prioridade, múltiplas GPUs |
| R-11 | Performance | Jobs CPU concorrendo com GPU | Médio | Média | Média | Filas separadas, recursos reservados |
| R-12 | Performance | Polling longo no frontend | Médio | Alta | Média | WebSocket/SSE para status |
| R-13 | Dados | Imutabilidade da cadeia dependente de trigger SQLite | Alto | Baixa | Alta | RLS/GRANT em PostgreSQL |
| R-14 | Dados | Chave Ed25519 dev efêmera | Alto | Média | Alta | Configurar `CUSTODY_SIGNING_PRIVATE_KEY` |
| R-15 | Dados | Lock de cadeia local ao processo | Médio | Média | Média | Lock distribuído para cadeia |
| R-16 | Dados | Soft-delete com remoção física de arquivos | Alto | Baixa | Alta | Backup antes de exclusão |
| R-17 | Operação | Sem Alembic | Médio | Alta | Alta | Adotar Alembic |
| R-18 | Operação | Sem observabilidade estruturada | Médio | Alta | Média | Métricas, logs estruturados, tracing |
| R-19 | Dependências | PyTorch/CUDA incompatível | Alto | Média | Alta | Fallback CPU, imagem GPU isolada |
| R-20 | Dependências | Modelos não versionados / links quebrados | Médio | Média | Média | Versionar pesos, espelhos |
| R-21 | Dependências | Vendor forks sem versionamento | Médio | Média | Média | Documentar versões e licenças |
| R-22 | Integridade | Placeholder de técnicas ML | Médio | Baixa | Média | Ocultar da UI até implementado |
| R-23 | Integridade | Não-determinismo de técnicas GPU | Médio | Média | Média | Documentar perfis de determinismo |
| R-24 | Segurança | Scripts de seed removem usuários | Alto | Baixa | Alta | Confirmar antes de executar em produção |
| R-25 | Segurança | Credenciais padrão em docker-compose | Alto | Baixa | Alta | Usar secrets/override em produção |
| R-26 | Integridade | Caso fechado ainda aceita uploads e submissões de jobs | Alto | Média | Alta | Adicionar validação em `EvidenceService` e `JobService` |
| R-27 | Integridade | `JobService.submit_job` não valida compatibilidade técnica vs. tipo de mídia | Médio | Média | Alta | Validar `evidence.file_type in plugin.supported_types` |
| R-28 | Integridade | Ciclo de vida de jobs não gera `CustodyRecord` | Alto | Alta | Alta | Adicionar `CustodyService.create_record` em início/conclusão/falha |
| R-29 | Operação | Dockerfile base com `--reload` usado em produção | Médio | Média | Média | Criar imagem de produção sem reload |
| R-30 | Operação | Nome do ambiente Conda diverge (`environment.yml` = `forensicauth`, `dev-stack.sh` = `va-suite`) | Baixo | Média | Baixa | Alinhar nome do ambiente |
| R-31 | Dependências | `Dockerfile.gpu` pode instalar `torch` de fontes conflitantes | Médio | Média | Média | Remover torch de `requirements-gpu.txt` ou usar índice CUDA consistente |

## Top 10 Riscos

1. **R-14** — Chave Ed25519 dev efêmera invalida valor probatório
2. **R-01** — SECRET_KEY padrão permite forjar tokens
3. **R-06** — PostgreSQL único sem replicação
4. **R-13** — Imutabilidade da cadeia não garantida em PostgreSQL
5. **R-02** — JWT em localStorage vulnerável a XSS
6. **R-10** — GPU singleton gargalo de throughput
7. **R-19** — Dependência de PyTorch/CUDA
8. **R-16** — Remoção física em soft-delete
9. **R-07** — Redis único ponto de falha
10. **R-17** — Sem Alembic

## SPOFs

1. PostgreSQL único
2. Redis único
3. Filesystem local compartilhado
4. Worker GPU único
5. GPU única

## Riscos de Dados

- Cadeia de custódia pode ser alterada em PostgreSQL sem mecanismo de imutabilidade
- Chave de assinatura dev é efêmera
- Backup deve incluir banco + filesystem
- Ciclo de vida de jobs não gera registros de custódia

## Riscos de Segurança

- SECRET_KEY padrão
- CORS permissivo
- Token em localStorage
- Upload de referências sem permissão de edição
- `torch.load(weights_only=False)`

## Riscos Operacionais

- Sem Alembic
- Sem observabilidade
- Scripts de seed destrutivos
- Deploy manual
- Dockerfile base com reload em produção
- Instalação GPU com fontes potencialmente conflitantes

## Risco Residual

Mesmo após mitigações, permanecem:
- Complexidade de deploy de ML
- Necessidade de especialistas forenses para interpretar resultados
- Dependência de hardware GPU para performance

## Evidências

- `src/backend/app/config.py`
- `src/backend/app/main.py`
- `src/backend/services/custody_service.py`
- `src/backend/services/custody_signing_service.py`
- `src/backend/app/database.py`
- `src/frontend/src/services/api.ts`
- `src/frontend/src/store/authStore.ts`
- `docker-compose.yml`
