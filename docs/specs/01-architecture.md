# 01-architecture.md - Especificacao Tecnica, Integracao e Contratos

## Diagrama da Arquitetura (Descricao Textual)

```
+------------------+         +---------------------+
|   React Frontend | <-----> |   FastAPI Backend   |
|   (Port 3000)    |  HTTP   |   (Port 8000)       |
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

## Stack Tecnologico Confirmado

| Camada | Tecnologia | Versao |
|--------|-----------|--------|
| Backend | FastAPI | >= 0.104 |
| Backend | Python | >= 3.11 |
| Backend | SQLAlchemy | >= 2.0 |
| Backend | Celery | >= 5.3 |
| Backend | PyMuPDF | >= 1.23 |
| Backend | jpegio | >= 0.2 |
| Backend | OpenCV | >= 4.8 |
| Backend | PyTorch | >= 2.0 |
| Frontend | React | 18 |
| Frontend | TypeScript | >= 5.0 |
| Banco | PostgreSQL | >= 15 |
| Fila | Redis | >= 7 |
| Deploy | Docker + Compose | - |

## Modelo de Dados (Entidades Principais)

### User
- id: UUID PK
- username: str UNIQUE NOT NULL
- email: str UNIQUE NOT NULL
- hashed_password: str NOT NULL
- role: enum [admin, perito, analista] NOT NULL
- is_active: bool DEFAULT true
- created_at: datetime
- updated_at: datetime

### Case
- id: UUID PK
- protocol_number: str UNIQUE NOT NULL
- title: str NOT NULL
- description: text
- created_by: UUID FK -> User
- assigned_to: UUID FK -> User (nullable, para analistas)
- status: enum [aberto, fechamento_pendente, fechado]
- created_at: datetime
- updated_at: datetime

### Evidence
- id: UUID PK
- case_id: UUID FK -> Case
- filename: str NOT NULL
- original_filename: str NOT NULL
- file_path: str NOT NULL
- file_size: int NOT NULL
- file_type: enum [imagem, audio, video, pdf]
- mime_type: str
- sha256: str NOT NULL (64 chars)
- uploaded_by: UUID FK -> User
- created_at: datetime

### AnalysisJob
- id: UUID PK
- evidence_id: UUID FK -> Evidence
- technique: str NOT NULL (ex: "prnu", "jpeg_ghosts", "sepael", "mp3_parser")
- status: enum [pending, running, completed, failed]
- parameters: JSONB NOT NULL
- result_path: str (nullable)
- result_sha256: str (nullable, 64 chars)
- started_at: datetime (nullable)
- completed_at: datetime (nullable)
- created_by: UUID FK -> User
- created_at: datetime
- error_message: text (nullable)

### CustodyRecord
- id: UUID PK
- record_type: str (evidence_upload, derivative_saved, case_shared, case_closed, ...)
- case_id: UUID FK -> Case
- evidence_id: UUID FK -> Evidence (nullable)
- job_id: UUID FK -> AnalysisJob (nullable)
- user_id: UUID FK -> User
- sha256_input: str (nullable)
- sha256_output: str (nullable)
- sha256_params: str (nullable)
- details: JSONB
- previous_record_hash: str (nullable)
- record_hash: str NOT NULL
- chain_sequence: int NOT NULL
- system_signature: str (nullable) -- Ed25519 sobre record_hash
- signing_key_id: str (nullable)
- timestamp: datetime NOT NULL

### CaseShare
- id: UUID PK
- case_id: UUID FK -> Case
- shared_with_user_id: UUID FK -> User
- role: enum [viewer, editor]
- shared_by: UUID FK -> User
- created_at, revoked_at: datetime

### CaseClosure
- id: UUID PK
- case_id: UUID FK -> Case
- closure_sequence: int
- manifest_sha256: str
- manifest_json: JSONB
- signature_mode: enum [system, icp_brasil]
- system_signature: str (nullable)
- signed_by: UUID FK -> User
- signed_at: datetime
- custody_record_id: UUID FK -> CustodyRecord (nullable)

### CaseClosureSignature
- id: UUID PK
- closure_id: UUID FK -> CaseClosure
- user_id: UUID FK -> User
- system_signature: str
- signed_at: datetime

### Report
- id: UUID PK
- case_id: UUID FK -> Case
- title: str NOT NULL
- file_path: str NOT NULL
- sha256: str NOT NULL
- generated_by: UUID FK -> User
- created_at: datetime

## APIs / Contratos (Endpoints Principais)

### Auth
- `POST /api/v1/auth/login` → Body: {username, password} → Response: {access_token, token_type, user: {id, username, role}}
- `POST /api/v1/auth/register` → Body: {username, email, password, role} → Response: User (Admin only)
- `GET /api/v1/auth/me` → Response: User atual

### Cases
- `GET /api/v1/cases` → Query: ?status=&assigned_to= → Response: List[Case]
- `POST /api/v1/cases` → Body: {protocol_number, title, description, assigned_to} → Response: Case
- `GET /api/v1/cases/{id}` → Response: Case + List[Evidence]
- `PUT /api/v1/cases/{id}` → Body: campos atualizaveis → Response: Case

### Evidence
- `POST /api/v1/evidence` → Form: file, case_id → Response: Evidence (com sha256)
- `GET /api/v1/evidence/{id}` → Response: Evidence + metadata
- `GET /api/v1/evidence/{id}/download` → Response: arquivo binario

### Analysis
- `POST /api/v1/analysis` → Body: {evidence_id, technique, parameters} → Response: AnalysisJob
- `GET /api/v1/analysis/{job_id}` → Response: AnalysisJob (status, resultado quando completo)
- `GET /api/v1/analysis/{job_id}/result` → Response: JSON/imagens/artefatos do resultado
- `GET /api/v1/analysis/techniques` → Response: List[technique_info] (tecnicas disponiveis por tipo de evidencia)

### Reports
- `POST /api/v1/reports` → Body: {case_id, title, job_ids[]} → Response: Report (job assincrono)
- `GET /api/v1/reports/{id}` → Response: Report
- `GET /api/v1/reports/{id}/download` → Response: PDF

### Audit
- `GET /api/v1/audit` → Query: ?case_id=&user_id=&from=&to= → Response: List[CustodyRecord]
- `GET /api/v1/audit/verify-case-forensic/{case_id}` → verificação ampliada (cadeia + arquivos + proveniência)
- `GET /api/v1/audit/signing-keys` → chave pública Ed25519

### Case sharing & lifecycle
- `POST/GET/DELETE /api/v1/cases/{id}/shares`
- `GET /api/v1/cases/shared-with-me`
- `POST /api/v1/cases/{id}/close` | `reopen` | `close/sign`

## Fluxo de Dados

1. **Upload de Evidencia**: Frontend → FastAPI → salva arquivo em disco → calcula SHA-256 → insere Evidence → insere CustodyRecord → retorna Evidence
2. **Submissao de Analise**: Frontend → FastAPI → cria AnalysisJob (status=pending) → publica Celery task → Redis → retorna job_id
3. **Execucao de Job**: Celery Worker consome task → atualiza job (status=running) → executa adapter forense → salva resultado → calcula SHA-256 do resultado → atualiza job (status=completed) → insere CustodyRecord
4. **Consulta de Resultado**: Frontend → FastAPI → busca AnalysisJob → se completed, le resultado do disco → retorna
5. **Geracao de Laudo**: Frontend → FastAPI → cria Report (async) → Celery gera PDF com WeasyPrint → calcula SHA-256 → insere CustodyRecord → notifica frontend

## Decisoes Arquiteturais (ADRs)

### ADR-001: Monolito Modular vs Microservicos
**Decisao**: Monolito modular (FastAPI monolitico com pacotes internos bem definidos).
**Justificativa**: Ambiente local/servidor unico. Microservicos adicionariam overhead de rede e complexidade desnecessaria. Isolamento e feito via pacotes Python (auth, core, adapters, services).

### ADR-002: PostgreSQL com JSONB para Parametros Flexiveis
**Decisao**: PostgreSQL relacional com colunas JSONB para parametros de jobs e registros de auditoria.
**Justificativa**: Permite schema rigido para entidades principais (User, Case, Evidence) com flexibilidade para parametros forenses que variam por tecnica. ACID garante integridade da cadeia de custodia.

### ADR-003: Celery + Redis para Fila de Jobs
**Decisao**: Celery com broker Redis e backend de resultados em Redis (ou PostgreSQL para persistencia).
**Justificativa**: Padrao de mercado para Python. Permite serializacao de jobs GPU, retry, prioridade e monitoramento via Flower.

### ADR-004: Preservacao de Bibliotecas Legadas via Adapters
**Decisao**: Bibliotecas forenses especificas dos notebooks legados sao preservadas intactas e encapsuladas em adapters.
**Justificativa**: Algoritmos forenses exigem exatidao. Adaptadores padronizam I/O sem alterar processamento interno. Testes de regressao garantem equivalencia.

### ADR-005: React SPA para Frontend
**Decisao**: Single Page Application com React 18 e TypeScript.
**Justificativa**: Melhor UX para dashboards, visualizacao de resultados forenses (imagens, graficos) e status de jobs em tempo real. Comunicacao via REST API.

## Estrategia de Deploy

- **Desenvolvimento**: Docker Compose com hot-reload (backend e frontend).
- **Producao**: Docker Compose no servidor corporativo da instituicao. Volumes montados para upload de evidencias e resultados.
- **Backup**: Dump diario do PostgreSQL + sincronizacao do volume de evidencias para OneDrive corporativo (excecao autorizada de nuvem).
