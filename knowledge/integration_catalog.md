# Integration Catalog — ForensicAuth

## Missão
Inventariar integrações do sistema.

## Tabela Principal

| Integração | Tipo | Direção | Criticidade | Status |
|---|---|---|---|---|
| PostgreSQL | Database | Bidirectional | Tier 0 | Ativa |
| Redis | Cache/Queue | Bidirectional | Tier 0 | Ativa |
| Filesystem Storage | Storage | Bidirectional | Tier 0 | Ativa |
| Celery Workers | Messaging | Outbound | Tier 0 | Ativa |
| GPU CUDA | AI Service | Outbound | Tier 1 | Ativa |
| Nginx (frontend) | Proxy | Inbound | Tier 1 | Ativa |
| Peritus Desktop | File Format | Bidirectional | Tier 2 | Ativa |
| VCP Package | File Format | Bidirectional | Tier 2 | Ativa |
| HuggingFace Hub | AI Service | Outbound | Tier 2 | Ocasiona (download) |
| gdown / Google Drive | AI Service | Outbound | Tier 2 | Ocasiona (download) |

## Integração: PostgreSQL

- Objetivo: Persistência relacional ACID
- Tipo: Database
- Direção: Bidirectional
- Dependências: SQLAlchemy, psycopg2-binary
- Fluxos Afetados: Todos os fluxos de dados
- SLA: Síncrono por request
- Timeout: Pool pre-ping
- Retry: Não
- Fallback: SQLite em dev
- Observabilidade: Logs SQLAlchemy em DEBUG
- Riscos: Banco único, sem replicação
- Criticidade: Tier 0
- Status: Ativa

## Integração: Redis

- Objetivo: Broker Celery, backend resultados, lock GPU, fila visível
- Tipo: Cache/Queue
- Direção: Bidirectional
- Dependências: redis-py, Celery
- Fluxos Afetados: Jobs assíncronos, serialização GPU
- SLA: Subsegundos
- Timeout: Configurável
- Retry: Celery retry
- Fallback: Thread local em SQLite
- Observabilidade: Flower (não confirmado ativo)
- Riscos: Redis único, perda de fila
- Criticidade: Tier 0
- Status: Ativa

## Integração: Filesystem Storage

- Objetivo: Armazenar uploads, resultados, derivados, modelos
- Tipo: Storage
- Direção: Bidirectional
- Dependências: OS filesystem, volumes Docker/NFS
- Fluxos Afetados: Upload, download, resultados, derivados
- SLA: Local
- Timeout: I/O de disco
- Retry: Não
- Fallback: Nenhum
- Observabilidade: Não
- Riscos: Storage local compartilhado, backup necessário
- Criticidade: Tier 0
- Status: Ativa

## Integração: Celery Workers

- Objetivo: Executar jobs assíncronos
- Tipo: Messaging
- Direção: Outbound (API publica, workers consomem)
- Dependências: Redis, Celery
- Fluxos Afetados: Análises forenses
- SLA: Assíncrono
- Timeout: Task timeout configurável
- Retry: Retry exponencial em tarefas
- Fallback: Thread local em SQLite
- Observabilidade: Logs Celery
- Riscos: Workers podem falhar, fila pode acumular
- Criticidade: Tier 0
- Status: Ativa

## Integração: GPU CUDA

- Objetivo: Inferência acelerada de modelos ML
- Tipo: AI Service
- Direção: Outbound
- Dependências: NVIDIA drivers, CUDA 12.4, PyTorch
- Fluxos Afetados: Análises ML (synthetic, deepfake, IMDL, etc.)
- SLA: Variável (segundos a minutos)
- Timeout: `GPU_LOCK_TTL_SECONDS` (padrão 3600s)
- Políticas adicionais: `GPU_DISTRIBUTED_LOCK`, `GPU_RESIDENT_TECHNIQUES`, `GPU_LRU_TTL_SECONDS`, `GPU_RESERVED_FUTURE_MB`, `GPU_MIN_FREE_MB`, `SYNTHETIC_KEEP_RESIDENT`, warmup por técnica
- Retry: Fallback CPU
- Fallback: CPU
- Observabilidade: `nvidia-smi`, healthcheck
- Riscos: OOM, singleton, driver incompatível, lock que pode expirar antes do job terminar
- Criticidade: Tier 1
- Status: Ativa

## Integração: Nginx (frontend)

- Objetivo: Servir SPA e fazer proxy reverso para API
- Tipo: Proxy
- Direção: Inbound
- Dependências: nginx
- Fluxos Afetados: Acesso web
- SLA: Síncrono
- Timeout: Padrão nginx
- Retry: Não
- Fallback: Nenhum
- Observabilidade: Logs nginx
- Riscos: Configuração de proxy
- Criticidade: Tier 1
- Status: Ativa

## Integração: Peritus Desktop

- Objetivo: Importar/exportar casos no formato legado Peritus
- Tipo: File Format
- Direção: Bidirectional
- Dependências: Parser de arquivos Peritus
- Fluxos Afetados: Importação/exportação de casos
- SLA: Assíncrono
- Timeout: Variável
- Retry: Não
- Fallback: Nenhum
- Observabilidade: Logs
- Riscos: Formato legado pode mudar
- Criticidade: Tier 2
- Status: Ativa

## Integração: VCP Package

- Objetivo: Exportar/importar pacotes forenses portáveis
- Tipo: File Format
- Direção: Bidirectional
- Dependências: ZIP, manifesto JSON
- Fluxos Afetados: Transferência de casos entre instâncias
- SLA: Assíncrono
- Timeout: Variável
- Retry: Não
- Fallback: Nenhum
- Observabilidade: Logs
- Riscos: Integridade do pacote
- Criticidade: Tier 2
- Status: Ativa

## Gate

De quem dependemos: PostgreSQL, Redis, Filesystem, GPU/CUDA (opcional), workers Celery.
Quem depende de nós: Frontend React, usuários finais, possíveis integrações Peritus/VCP.

## Evidências

- `docker-compose.yml`
- `docker-compose.gpu.yml`
- `src/backend/app/celery_app.py`
- `src/backend/app/config.py`
- `src/frontend/nginx.conf`
- `src/frontend/Dockerfile`
