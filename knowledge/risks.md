# Risks — ForensicAuth

## Matriz

| ID | Categoria | Risco | Impacto | Probabilidade | Prioridade | Mitigação |
|---|---|---|---|---|---|---|
| R01 | Segurança | SECRET_KEY padrão fraco em exemplos | Alto | Alta | P0 | Rotacionar em produção |
| R02 | Segurança | JWT sem refresh token / revogação | Alto | Média | P1 | Implementar refresh/logout |
| R03 | Segurança | CORS permissivo (`*`) | Médio | Média | P1 | Restringir origens |
| R04 | Segurança | Token JWT em localStorage | Médio | Média | P2 | Considerar HttpOnly cookie |
| R05 | Segurança | `torch.load(weights_only=False)` | Alto | Alta | P1 | Ativar `weights_only=True` |
| R06 | Disponibilidade | PostgreSQL único (SPOF) | Alto | Baixa | P1 | Replicação/backup |
| R07 | Disponibilidade | Redis único (SPOF) | Alto | Baixa | P1 | Replicação/Sentinel |
| R08 | Disponibilidade | Filesystem local compartilhado | Alto | Média | P1 | Volumes/NFS/backup |
| R09 | Escalabilidade | GPU singleton (um job por vez) | Alto | Alta | P0 | Múltiplas GPUs/filas |
| R10 | Performance | Workers GPU residentes podem OOM | Alto | Média | P1 | Monitorar VRAM, TTL |
| R11 | Integridade | Sem Alembic; schema evolui ad-hoc | Alto | Média | P1 | Adotar Alembic |
| R12 | Integridade | Imutabilidade de custódia depende de trigger SQLite | Alto | Baixa | P1 | Políticas PostgreSQL |
| R13 | Dados | `tests/fixtures/` vazio | Médio | Média | P2 | Popular fixtures |
| R14 | Dependências | Modelos grandes não versionados | Alto | Alta | P1 | Registry/model manifest |
| R15 | Dependências | Vendors com `sys.path` manipulado | Médio | Alta | P1 | Isolamento por pacotes |
| R16 | Operação | Dockerfile padrão com `--reload` | Médio | Média | P2 | Imagem de produção |
| R17 | Operação | Sem `.dockerignore` | Médio | Alta | P1 | Criar `.dockerignore` |
| R18 | Operação | 92 arquivos não commitados, 1 commit no histórico | Alto | Alta | P0 | Commitar/documentar |
| R19 | Observabilidade | Sem métricas/tracing/alertas | Alto | Média | P1 | Adicionar observability |
| R20 | ML | `deepfake_similarity` é placeholder | Alto | Média | P1 | Finalizar ou remover |
| R21 | ML | STIL sem peso treinado | Médio | Média | P2 | Treinar/obter peso |
| R22 | ML | IMDL-BenCo ecosystem methods faltando pesos/vendors | Médio | Alta | P1 | Checklist de downloads |
| R23 | ML | Ausência de drift monitoring | Médio | Baixa | P2 | Implementar monitoramento |
| R24 | Testabilidade | E2E de ML dependem de GPU/modelos | Alto | Média | P1 | Mocks/CI condicional |
| R25 | Testabilidade | Frontend com páginas muito grandes | Médio | Alta | P2 | Refatorar componentes |
| R26 | Segurança | JWT armazenado em `localStorage` | Médio | Alta | P1 | HttpOnly cookie |
| R27 | Segurança | `torch.load(weights_only=False)` em ~22 pipelines legados | Alto | Alta | P0 | Migrar para `weights_only=True` |
| R28 | Segurança | Credenciais padrão em `docker-compose.yml` | Alto | Alta | P0 | Usar secrets/variáveis de ambiente |
| R29 | Disponibilidade | Nginx frontend sem `client_max_body_size` definido | Médio | Média | P2 | Configurar limites de upload |
| R30 | Testabilidade | Teste frontend `caseAnalysisNav.test.ts` quebrado | Médio | Alta | P1 | Corrigir rota desatualizada |
| R31 | Operação | Ambiente conda divergente (`forensicauth` vs `va-suite`) | Baixo | Média | P3 | Alinhar scripts e `environment.yml` |
| R32 | Segurança/Forense | Pesos do ensemble `synthetic_image_detection` sem checksums SHA-256 | Alto | Alta | P0 | Criar `manifest.json` e validar no startup |
| R33 | Confiabilidade | `synthetic_image_detection` sem score final consolidado | Médio | Alta | P1 | Implementar ensemble_score |
| R34 | Confiabilidade | Modelos legados/testados (CLIDE, SAFE, Effort, XGBoost, NPR) presentes no runtime | Baixo | Média | P3 | Remover do runtime ou mover para backup versionado |
| R35 | Operação | Commit acidental de `outputs/` ou pesos >100 MB bloqueia push GitHub | Alto | Média | P0 | `.gitignore` reforçado jul/2026; nunca versionar artefatos |
| R36 | Operação | Git LFS >2 GB (DF Arena 4.6 GB) rejeitado pelo GitHub | Alto | Alta | P0 | Baixar via HuggingFace/scripts; não commitar |
| R37 | ML | Detectores spoofing áudio discordam (DF Arena vs WeDefense) | Médio | Alta | P2 | Documentar; meta-fusão/LR futuro |
| R38 | ML | Agregação por janelas ≠ protocolo original dos autores | Médio | Média | P2 | Modo "compatível autores" (64600 samples) |

## Top 10 Riscos

1. **R09 GPU singleton** — gargalo de throughput de análises ML
2. **R27 `torch.load(weights_only=False)`** — risco de execução de código arbitrário em ~22 pipelines
3. **R32 Pesos sem checksums** — integridade dos modelos forenses não verificável
4. **R01 SECRET_KEY padrão** — comprometimento de segurança
5. **R28 Credenciais padrão em docker-compose** — risco de deploy inseguro
6. **R14 Modelos não versionados** — reproducibilidade forense comprometida
7. **R18 Dirty tree / histórico de commits curto** — risco de perda/auditoria
8. **R11 Sem Alembic operacional** — divergência de schema
9. **R06/R07/R08 SPOFs** — PostgreSQL, Redis, filesystem
10. **R20 deepfake_similarity placeholder / R33 ensemble sem score final** — funcionalidades ML incompletas

## Riscos de Dados

- Perda de evidências por falha de storage
- Inconsistência de schema entre ambientes
- Cadeia de custódia quebrada por bug em hash/assinatura
- Fixtures vazias dificultam testes de regressão

## Riscos de Segurança

- SECRET_KEY padrão em deploys apressados
- JWT em localStorage exposto a XSS
- CORS permissivo permite origens não autorizadas
- `torch.load` com `weights_only=False`
- Chaves Ed25519 de dev persistidas em disco

## Riscos Operacionais

- Builds Docker lentos por ausência de `.dockerignore`
- Worker GPU remoto depende de NFS com paths idênticos
- GPU residente/LRU aumenta complexidade de VRAM
- Nome inconsistente do ambiente conda (`va-suite` vs `forensicauth`)

## Risco Residual

- Mesmo com mitigações, a natureza forense exige validação rigorosa de qualquer mudança em algoritmos legados (Regra Máxima 8).

## Evidências

- `src/backend/app/config.py`
- `src/backend/core/gpu_inference.py`
- `src/backend/core/plugins/deepfake_adapter.py`
- `src/backend/core/legacy/stil/stil_runtime.py`
- `docker-compose.yml`
- `git status`, `git log`
