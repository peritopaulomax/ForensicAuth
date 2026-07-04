# System Brain — ForensicAuth

## Arquitetura em 60 Segundos

```text
Perito/Admin → React SPA → FastAPI → Services → PostgreSQL/Redis/FS
                                    ↓
                           Celery Workers → Plugins → Legacy/Vendor/Models
```

## Componentes Críticos

| Componente | Tier | Função |
|---|---|---|
| FastAPI App | 0 | API, lifespan, routers |
| PostgreSQL | 0 | Estado e cadeia de custódia |
| Redis | 0 | Fila Celery, backend, lock GPU |
| Filesystem | 0 | uploads, results, derivatives, models |
| CustodyService | 0 | Cadeia SHA-256 + Ed25519 |
| EvidenceService | 0 | Upload, hash, soft-delete |
| JobService | 0 | Jobs e reproducibilidade |
| PluginRegistry | 1 | Descoberta de adapters |
| GPUInference | 1 | Fallback CPU/GPU, serialização |
| GPUResidency | 1 | Cache LRU de modelos residentes em GPU |
| `ml_gpu_job_slot` | 1 | Semáforo por slot GPU (via Redis/ThreadLocal) |
| `gpu_distributed_lock` | 1 | Lock distribuído Redis para execução GPU |
| React SPA | 1 | Interface web |

## Fluxos Críticos

1. **Upload** → SHA-256 → `Evidence` + `CustodyRecord`
2. **Análise** → `AnalysisJob` → Celery/thread → plugin → resultado (sem `CustodyRecord` atualmente)
3. **Derivado** → `Evidence` derivada + provenance + `CustodyRecord`
4. **Verificação forense** → cadeia + arquivos + assinaturas
5. **Fechamento** → manifesto + assinaturas + `CustodyRecord`
6. **Login** → JWT HS256

## Dependências Críticas

PostgreSQL 15, Redis 7, PyTorch/CUDA 12.4, filesystem, jpegio, PyMuPDF, librosa.

## Dados Críticos

| Dado | Onde | Risco |
|---|---|---|
| CustodyRecord | PostgreSQL | Imutabilidade não garantida em PG |
| Evidence | PostgreSQL + FS | Perda de FS = perda de evidência |
| AnalysisJob | PostgreSQL | Não gera custódia |
| Modelos | FS `models/` | ~43 GB, não versionados |
| `synthetic_image_detection` | GPU ensemble | `torch.load` inseguro no NPR legado, sem checksums, sem score consolidado |

## Top 10 Riscos (atualizado 2026-06-29)

1. GPU singleton / lock distribuído com fallback thread-local
2. `torch.load(weights_only=False)` em ~22 pipelines legados
3. PostgreSQL único
4. Credenciais padrão em docker-compose
5. Modelos não versionados (~43 GB)
6. Imutabilidade da cadeia dependente de trigger SQLite (PG pendente)
7. JWT em localStorage
8. Chave Ed25519 dev auto-gerada (persistida, mas não auditada)
9. SECRET_KEY padrão fraco
10. Observabilidade ausente

## Top 10 Dívidas (atualizado 2026-06-29)

1. Testes de regressão forense ausentes
2. Módulo de laudos/relatórios planejado mas não implementado
3. Frontend com páginas grandes e rotas legadas
4. Observabilidade ausente
5. Dockerfile base ainda usa `--reload`
6. docker-compose base ainda usa credenciais padrão
7. Modelos não versionados
8. Cobertura de testes frontend insuficiente (26% global)
9. Schemas Pydantic inline nos endpoints
10. Migrations ad-hoc coexistindo com Alembic

## Decisões Chave

- Monólito modular: ambiente local/servidor único
- PostgreSQL + JSONB: schema rígido + flexibilidade
- Celery + Redis: serialização GPU, retry
- Adapters para legados: preservar algoritmos
- React SPA: UX para dashboards
- Jobs são previews exploratórios: não geram CustodyRecord (cadeia cobre upload, derivados, fechamento)
- Alembic adotado para migrações em produção

## Roadmap

1. Corrigir `torch.load(weights_only=False)` em pipelines legados (validar equivalência forense)
2. Testes de regressão forense contra notebooks legados
3. Observabilidade (logs estruturados, métricas, health checks)
4. Versionamento e validação de modelos/pesos (checksums SHA-256)
5. Finalizar módulo de laudos/relatórios
6. Refatorar roteamento legado do frontend
7. Implementar score ensemble consolidado para `synthetic_image_detection`
8. Limpar modelos legados não utilizados (XGBoost/NPR/CLIDE/SAFE/Effort) do runtime
