# Architecture — ForensicAuth

## Metadados

| Campo | Valor |
|---|---|
| Status | Ativo |
| Última Atualização | 2026-06-29 (consolidado via /analisar-repositorio-multiagente) |
| Confiança Geral | Alta |
| Autor | ForensicAuth Team |
| Versão | 1.1 |

## Resumo Executivo

O ForensicAuth é uma plataforma forense digital para peritos criminais da instituição cliente. Resolve o problema de consolidar análises técnicas de imagem, áudio, vídeo e PDF em um ambiente web auditável, com cadeia de custódia digital rastreável, jobs assíncronos e geração de laudos.

Em alto nível:

```text
Usuário (Perito/Analista/Admin)
↓
React SPA (porta 3000 / nginx 80)
↓ HTTP /api/v1
FastAPI Backend (porta 8000)
↓
Camada de Serviços (casos, evidências, jobs, custódia)
↓
Plugins Forenses (CPU/GPU) + Legados/Vendor + Modelos ML
↓
PostgreSQL + Redis + Filesystem
```

## Classificação

- **Monólito Modular** (FastAPI)
- **ML Platform** (dezenas de modelos forenses)
- **Frontend SPA** (React + TypeScript)
- **API REST**
- **Data Platform** forense (evidências, resultados, laudos)

## Visão Arquitetural

```text
+------------------+         +---------------------+
|   React Frontend | <-----> |   FastAPI Backend   |
|   (Port 3000/80) |  HTTP   |   (Port 8000)       |
+------------------+         +---------------------+
                                      |
                    +-----------------+-----------------+
                    |                 |                 |
            +-------v------+  +-------v------+  +-------v-------+
            |  PostgreSQL  |  |    Redis     |  | Celery Worker |
            |   (Port 5432)|  |   (Port 6379)|  |   (GPU/CPU)   |
            +--------------+  +--------------+  +---------------+
                    |                                    |
            +-------v-------+                    +-------v-------+
            |  Audit Log    |                    |  Legados/     |
            |  (Imutavel)   |                    |  (Adapters)   |
            +---------------+                    +---------------+
```

## Componentes

| Componente | Responsabilidade | Criticidade | Status |
|---|---|---|---|
| API FastAPI | Expor endpoints REST, autenticação, validação | Tier 0 | Ativo |
| Frontend React | Interface do perito, visualização de resultados | Tier 1 | Ativo |
| PostgreSQL | Persistência relacional ACID | Tier 0 | Ativo |
| Redis | Broker Celery, backend resultados, lock GPU | Tier 0 | Ativo |
| Worker CPU | Jobs leves e técnicas CPU | Tier 1 | Ativo |
| Worker GPU | Jobs de inferência ML | Tier 1 | Ativo |
| Plugin Registry | Descoberta e registro de adapters | Tier 1 | Ativo |
| ForensicPlugin | Contrato base de adapters | Tier 1 | Ativo |
| Legacy Pipelines | Algoritmos forenses originais | Tier 1 | Ativo |
| Custody Service | Cadeia de custódia SHA-256 + Ed25519 | Tier 0 | Ativo |
| Job Service | Orquestração de jobs e reproducibilidade | Tier 0 | Ativo |
| Evidence Service | Upload, hash, tipo, soft-delete | Tier 0 | Ativo |
| Case Lifecycle Service | Fechamento, manifesto, assinaturas | Tier 1 | Ativo |
| Forensic Integrity Service | Verificação forense completa | Tier 1 | Ativo |
| Derivative Service | Promover artefatos a evidências | Tier 1 | Ativo |
| GPU Inference | Fallback CPU/GPU, serialização | Tier 1 | Ativo |

## Camadas

| Camada | Diretórios |
|---|---|
| Presentation | `src/frontend/src/pages`, `src/frontend/src/components` |
| Application | `src/backend/api/v1/endpoints`, `src/backend/services` |
| Domain | `src/backend/models`, regras em services |
| Infrastructure | `src/backend/app`, `src/backend/core`, `src/backend/tasks`, Docker |

## Frontend

| Aspecto | Detalhe |
|---|---|
| Tecnologia | React 18 + TypeScript |
| Entrypoint | `src/frontend/src/main.tsx` |
| Build | Vite 5 |
| Deploy | Nginx via Docker multi-stage |
| Roteamento | React Router v6 |
| Estado Global | Zustand (auth) |
| Estado Remoto | TanStack Query (uso parcial) |
| HTTP Client | Axios + interceptores JWT |
| Testes | Vitest + React Testing Library + Playwright |

## Backend

| Aspecto | Detalhe |
|---|---|
| Tecnologia | Python 3.11+ |
| Entrypoint | `src/backend/app/main.py` |
| Framework | FastAPI >= 0.104 |
| ORM | SQLAlchemy 2.x |
| Validação | Pydantic v2 |
| Auth | JWT HS256 + bcrypt |
| Workers | Celery + Redis |

## Workers

| Worker | Fila | Responsabilidade |
|---|---|---|
| worker-cpu | `celery` | Técnicas CPU-only, 4 concorrentes (configurável) |
| worker-gpu | `gpu` | Técnicas ML/GPU, 1 concorrente (serializado por lock Redis + thread lock) |

## Banco de Dados

| Tecnologia | PostgreSQL 15 (produção), SQLite (dev/testes) |
| Responsabilidade | Persistência de entidades e cadeia de custódia |
| Criticidade | Tier 0 |

## Cache

| Tecnologia | Redis 7 |
| Uso | Broker Celery, backend resultados, lock distribuído GPU, fila visível |
| Dependências | worker-cpu, worker-gpu, app |

## Storage

| Tecnologia | Filesystem local (volumes Docker/NFS) |
| Objetos | uploads, results, derivatives, peritus_cases, models |
| Criticidade | Tier 0 |

## Autenticação

| Método | JWT HS256 |
| Provedor | Backend próprio |
| Fluxos | login, first-access, register (admin) |

## Autorização

| Papéis | admin, perito |
| Permissões | admin: CRUD usuários; perito: casos/evidências/análises; analista (legado): viewer |
| Restrições | Casos fechados são imutáveis; compartilhamento viewer/editor |

## Observabilidade

| Logs | Logging padrão Python/FastAPI; logs de debug rotativos no diretório de dados da aplicação |
| Métricas | Não há métricas estruturadas observadas |
| Tracing | Não há tracing distribuído |
| Alertas | Não há alertas configurados |
| Healthchecks | Não há healthchecks estruturados nos containers |

## Fluxos Principais

### 1. Upload de Evidência
- Entrada: `POST /api/v1/evidences/upload`
- Validação de caso, tipo MIME, tamanho <= 500MB
- Cálculo SHA-256, salvamento em disco
- Criação de `Evidence` e `CustodyRecord` assinado

### 2. Submissão e Execução de Análise
- Entrada: `POST /api/v1/analysis`
- Criação de `AnalysisJob` (pending)
- Roteamento CPU/GPU; fila Celery ou thread local
- Execução do plugin, staging de artefatos, cálculo de hash
- Atualização para completed/failed (CustodyRecord ainda não gerado no código atual)

### 3. Salvar Derivado
- Entrada: `POST /api/v1/evidences/derivatives`
- Promove artefato de job para evidência derivada
- Provenance snapshot, novo SHA-256, CustodyRecord

### 4. Verificação Forense
- Entrada: `GET /api/v1/audit/verify-case-forensic/{case_id}`
- Verifica cadeia, assinaturas, arquivos no disco, provenance, fechamentos

### 5. Geração de Laudo
- Entrada: `POST /api/v1/reports` (especificado; implementação parcial)

### 6. Fechamento de Caso
- Entrada: `POST /api/v1/cases/{id}/close` e `/close/sign`
- Gera manifesto, assinaturas, atualiza status

### 7. Compartilhamento de Caso
- Entrada: `/api/v1/cases/{id}/shares`
- Viewer/editor com controle de acesso

### 8. Transferência VCP / Peritus
- Entrada: `/api/v1/case-transfer/*`, `/api/v1/peritus-transfer/*`
- Export/import de pacotes forenses

## Dependências Críticas

| Dependência | Tipo | Criticidade | Impacto |
|---|---|---|---|
| PostgreSQL | Banco | Tier 0 | Indisponibilidade para todo o sistema |
| Redis | Cache/Fila | Tier 0 | Sem fila de jobs e lock GPU |
| PyTorch + CUDA | ML | Tier 1 | Sem técnicas GPU |
| Filesystem storage | Storage | Tier 0 | Sem acesso a evidências/resultados |
| jpegio, libzero, etc. | Forense | Tier 1 | Sem técnicas específicas |

## Pontos Únicos de Falha

1. Banco PostgreSQL único (sem replicação observada)
2. Redis único (broker e backend Celery)
3. Filesystem local compartilhado (não há object storage)
4. GPU singleton (apenas um job GPU por vez)
5. Worker GPU único (não há suporte a múltiplas GPUs)

## Riscos Arquiteturais

| Risco | Impacto | Probabilidade | Mitigação |
|---|---|---|---|
| Lock GPU singleton | Gargalo de throughput | Alta | Fila por prioridade, worker adicional |
| Storage local compartilhado | Falha em multi-réplica | Média | Volumes compartilhados/NFS |
| SQLite em produção tolerado | Perda de dados/escala | Baixa | Documentação recomenda PostgreSQL |
| Alembic em bootstrap + migrations ad-hoc | Divergência de schema | Média | Adotar Alembic puro |
| Secrets padrão em exemplos | Comprometimento de segurança | Média | Revisão manual em deploy |
| Chave Ed25519 dev auto-gerada | Perda de valor probatório | Média | Configurar em `.env` |
| `torch.load(weights_only=False)` | Execução de código arbitrário | Alta | Migrar para `weights_only=True` |
| Token JWT em localStorage | XSS expõe sessão | Média | HttpOnly cookie ou equivalente |

## Dívida Arquitetural

| Dívida | Impacto | Prioridade |
|---|---|---|
| Alembic em bootstrap + migrations ad-hoc | Evolução de schema frágil | Alta |
| `.dockerignore` criado mas Dockerfile base ainda usa `--reload` | Builds e deploy mistos | Alta |
| CORS permissivo | Risco de segurança | Média |
| JWT sem refresh token | UX e segurança | Média |
| Sem observabilidade estruturada | Dificuldade operacional | Média |
| Páginas frontend muito grandes | Manutenibilidade | Média |
| GPU singleton | Escalabilidade | Alta |

## Inconsistências

- `alembic` está em `requirements.txt` mas não é usado como motor principal de migrations.
- Dockerfile padrão usa `--reload` (indicador de dev), não produção.
- Algumas técnicas (`deepfake_similarity`, métodos IMDL ecosystem) são placeholders ou não totalmente integrados.
- Upload de referências não sempre exige permissão de edição do caso.

## Confiabilidade

Alta para o backend (código bem estruturado, testes unitários extensivos). Média para ML/legados (dependências de pesos e vendors complexos). Média para frontend (páginas grandes e testes insuficientes).
