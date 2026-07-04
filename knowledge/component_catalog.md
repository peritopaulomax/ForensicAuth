# Component Catalog — ForensicAuth

## Tabela Principal

| Componente | Tipo | Responsabilidade | Criticidade | Status |
|---|---|---|---|---|
| FastAPI App | Backend | Bootstrap da API, lifespan, routers | Tier 0 | Ativo |
| AuthService | Service | Autenticação JWT, bcrypt, first-access | Tier 0 | Ativo |
| UserService | Service | Provisionamento/reset de usuários | Tier 0 | Ativo |
| CaseAccess | Service | RBAC de casos/evidências/jobs | Tier 0 | Ativo |
| EvidenceService | Service | Upload, hash, tipo, soft-delete | Tier 0 | Ativo |
| JobService | Service | Submeter, executar, reproduzir jobs | Tier 0 | Ativo |
| JobRunner | Service | Escalonamento Celery/thread | Tier 1 | Ativo |
| CustodyService | Service | Cadeia SHA-256 e verificação | Tier 0 | Ativo |
| CustodySigningService | Service | Assinatura Ed25519 | Tier 0 | Ativo |
| CaseLifecycleService | Service | Fechamento, manifesto, assinaturas | Tier 1 | Ativo |
| CaseDeletionService | Service | Soft-delete de casos | Tier 1 | Ativo |
| DerivativeService | Service | Promover artefatos a evidências | Tier 1 | Ativo |
| ForensicIntegrityService | Service | Verificação forense completa | Tier 1 | Ativo |
| GPUQueueService | Service | Visibilidade da fila GPU | Tier 2 | Ativo |
| PRNUFingerprintService | Service | Fingerprints por caso | Tier 2 | Ativo |
| CaseTransferService | Service | Export/import VCP | Tier 2 | Ativo |
| PeritusBridgeService | Service | Integração Peritus Desktop | Tier 2 | Ativo |
| PluginRegistry | Core | Descoberta de plugins | Tier 1 | Ativo |
| ForensicPlugin | Core | Contrato base de adapters | Tier 1 | Ativo |
| GPUInference | Core | Fallback CPU/GPU, slot serializado | Tier 1 | Ativo |
| GPULock | Core | Lock distribuído Redis para GPU | Tier 1 | Ativo |
| GPUResidency | Core | Política de residência LRU de modelos GPU, com configuração por técnica, detecção de pressão de VRAM e purga condicional de caches estrangeiros | Tier 1 | Ativo |
| FakeVlmAdapter | Core | Adapter para detecção com FakeVLM | Tier 2 | Ativo |
| ClipBasedSyntheticAdapter | Core | Adapter para detecção CLIP-based de imagens sintéticas | Tier 2 | Ativo |
| JobDispatch | Core | Roteamento CPU/GPU | Tier 1 | Ativo |
| JobStaging | Core | Diretório de staging por job | Tier 1 | Ativo |
| JobArtifacts | Core | Normalização de artefatos | Tier 1 | Ativo |
| Reproducibility | Core | Manifestos, hashes, recibos | Tier 1 | Ativo |
| TechniqueRuntime | Core | Probes de disponibilidade | Tier 2 | Ativo |
| TechniqueIds | Core | IDs canônicos e aliases | Tier 2 | Ativo |
| PostgreSQL | Database | Persistência ACID | Tier 0 | Ativo |
| Redis | Cache/Queue | Broker Celery, lock, fila | Tier 0 | Ativo |
| Celery Worker CPU | Worker | Jobs leves | Tier 1 | Ativo |
| Celery Worker GPU | Worker | Jobs ML/GPU | Tier 1 | Ativo |
| React SPA | Frontend | Interface web | Tier 1 | Ativo |
| Axios API Client | Frontend | HTTP + JWT | Tier 1 | Ativo |
| Zustand Auth Store | Frontend | Estado de autenticação | Tier 1 | Ativo |
| Nginx | Frontend | Serve SPA e proxy API | Tier 1 | Ativo |

## Componente: FastAPI App

- Tipo: Backend
- Entrypoints: `src/backend/app/main.py`
- Dependências: AuthService, routers, config, database
- Dependentes: Todos os endpoints
- Fluxos: Recebe requisições HTTP e delega a endpoints
- Dados: Request/response JSON, FormData
- Riscos: CORS permissivo, SECRET_KEY padrão

## Componente: JobService

- Tipo: Service
- Entrypoints: `src/backend/services/job_service.py`
- Dependências: Evidence, AnalysisJob, plugins, filesystem, GPUInference
- Dependentes: analysis endpoints, Celery tasks
- Fluxos: Submeter → executar → stage → reproducibilidade
- Dados: AnalysisJob, result.json, artefatos
- Riscos: Acoplamento com parâmetros por técnica

## Componente: CustodyService

- Tipo: Service
- Entrypoints: `src/backend/services/custody_service.py`
- Dependências: PostgreSQL/SQLite, CustodySigningService
- Dependentes: EvidenceService, JobService, CaseLifecycleService
- Fluxos: Criar registro → encadear hash → assinar
- Dados: CustodyRecord
- Riscos: RLock process-local pode não escalar

## Componente: PluginRegistry

- Tipo: Core
- Entrypoints: `src/backend/core/plugin_registry.py`
- Dependências: Plugins em `core/plugins/`
- Dependentes: JobService, analysis endpoints
- Fluxos: Descobrir → instanciar → registrar
- Dados: Dicionário de plugins ativos
- Riscos: `sys.path` manipulado por vendors, falhas silenciosas

## Componente: GPUInference

- Tipo: Core
- Entrypoints: `src/backend/core/gpu_inference.py`
- Dependências: PyTorch, CUDA, config
- Dependentes: Plugins GPU, Celery tasks
- Fluxos: Resolver device → fallback CPU → executar → liberar
- Dados: Tensor/PIL/numpy
- Riscos: Serialização singleton, OOM

## Componente: React SPA

- Tipo: Frontend
- Entrypoints: `src/frontend/src/main.tsx`, `src/frontend/src/App.tsx`
- Dependências: React, Vite, Axios, Zustand
- Dependentes: Navegador do usuário
- Fluxos: Login → casos → evidências → análise → resultados
- Dados: JSON da API, blobs de artefatos
- Riscos: Páginas grandes, token em localStorage

## Gate

Componentes críticos identificados: API, banco, Redis, fila, cadeia de custódia, orquestração de jobs e plugins forenses.

## Evidências

- `src/backend/app/main.py`
- `src/backend/services/*.py`
- `src/backend/core/*.py`
- `src/frontend/src/App.tsx`
