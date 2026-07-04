# Domain Model — ForensicAuth

## Metadados

| Campo | Valor |
|---|---|
| Status | Ativo |
| Última Atualização | 2026-06-29 (consolidado via /analisar-repositorio-multiagente) |
| Confiança Geral | Alta |

## Resumo

Domínio forense digital: gestão de casos periciais, evidências digitais, análises técnicas, cadeia de custódia rastreável e laudos.

## Atores

| Ator | Papel |
|---|---|
| Admin | Gestão de usuários, configurações, auditoria completa |
| Perito | Cria casos, submete evidências, executa técnicas, gera laudos |
| Analista (legado) | Especificação prevê viewer, mas role foi migrada para `perito` em `db_migrations.py` |
| Sistema | Assina registros de custódia, executa jobs, gera hashes |

## Entidades

| Entidade | Responsabilidade |
|---|---|
| User | Credenciais, perfil (admin/perito), estado ativo |
| Case | Container forense com protocolo, status, compartilhamentos, storage_mode (`forensicauth` ou `peritus`) |
| Evidence | Arquivo digital submetido (original ou derivado) com SHA-256 |
| AnalysisJob | Tarefa de análise forense, status, parâmetros, resultado |
| CustodyRecord | Registro INSERT-only da cadeia de custódia |
| Report | Laudo PDF gerado com hash registrado (modelo existe; service/endpoint não implementado) |
| CaseShare | Compartilhamento viewer/editor de caso |
| CaseClosure | Fechamento/assinatura de caso |
| CaseClosureSignature | Assinatura adicional no fechamento |

> Nota: `PRNUFingerprint` não é uma entidade separada; fingerprints PRNU são armazenados como `Evidence` derivada com `extra_metadata["artifact_role"] == "prnu_fingerprint"`.

> Nota: A imutabilidade de `CustodyRecord` é garantida por trigger SQLite em dev/test; para PostgreSQL em produção o mecanismo ainda está pendente (RLS/policy/trigger equivalente).

## Estados

### Case
- `aberto`
- `fechamento_pendente`
- `fechado`

### Evidence
- Ativa / Soft-deleted
- Tipos: `imagem`, `audio`, `video`, `pdf`, `documento`
- Origem: `upload`, `derived`, `peritus`

### AnalysisJob
- Estados convencionados (modelo usa `String(20)`, não `Enum`):
  - `pending`
  - `running`
  - `completed`
  - `failed`
  - `purged` (aplicado apenas em exclusão de caso)

### User
- `password_set` true/false
- `role`: admin, perito
- `is_active`

## Eventos

| Evento | Consequência |
|---|---|
| Evidência enviada | Cria Evidence + CustodyRecord |
| Job submetido | Cria AnalysisJob pending |
| Job iniciado | Status running, timestamp |
| Job concluído | Status completed, artefatos, result_sha256 |
| Job falho | Status failed, mensagem de erro |

> Nota: o ciclo de vida de jobs (início/conclusão/falha) **não gera `CustodyRecord`** no código atual; apenas uploads, derivados, fechamentos e compartilhamentos geram registros de custódia.
| Derivado salvo | Nova Evidence derivada + provenance |
| Caso fechado | CaseClosure + manifesto + assinaturas |
| Caso reaberto | Cria registro `case_reopened`, status volta a `aberto` |
| Caso compartilhado | CaseShare criada |
| Caso excluído | Soft-delete, arquivos removidos, cadeia preservada |

## Regras de Negócio

| ID | Regra | Criticidade |
|---|---|---|
| RN-01 | Todo arquivo submetido DEVE ter SHA-256 calculado antes de processamento | Alta |
| RN-02 | Todo processamento forense DEVE registrar usuário, timestamp, técnica, parâmetros, hashes | Alta |
| RN-03 | Cadeia de custódia é INSERT-only; nenhum registro alterado/excluído | Alta |
| RN-04 | Jobs GPU DEVEM ser serializados (um por vez) | Alta |
| RN-05 | Analista não pode criar casos (perfil legado) | Média |
| RN-06 | Apenas Admin pode criar usuários | Alta |
| RN-07 | Relatórios PDF gerados DEVEM ser imutáveis | Alta |
| RN-08 | Bibliotecas forenses legadas NÃO podem ser substituídas sem teste de equivalência | Alta |
| RN-09 | Caso fechado não deve permitir novas evidências/análises | Alta |
| RN-10 | Evidências duplicadas ativas são rejeitadas no mesmo caso | Média |
| RN-11 | Tamanho máximo de upload: 500MB | Média |
| RN-12 | Apenas técnicas compatíveis com o tipo de mídia devem ser aplicadas | Alta |
| RN-13 | Schemas Pydantic devem estar centralizados em `src/backend/schemas/` | Média |
| RN-14 | `CustodyRecord.record_type` deve ser enum/registry validado | Média |

> Nota: RN-09 e RN-12 estão declaradas como regras desejadas, mas **não são validadas** em `EvidenceService.upload_evidence` nem em `JobService.submit_job` no código atual.
> Nota: RN-13 e RN-14 identificam dívidas técnicas: schemas estão inline nos endpoints e `record_type` é string livre.

## Contratos

- `POST /auth/login` → JWT + perfil
- `POST /auth/register` → User (admin only)
- `GET /auth/me` → User atual
- `GET /cases` → Lista de casos acessíveis
- `POST /cases` → Case criado
- `GET /cases/{id}` → Case + evidências
- `POST /evidences/upload` → Evidence com SHA-256
- `GET /evidences/{id}/download` → arquivo binário
- `POST /analysis` → AnalysisJob pending
- `GET /analysis/{job_id}` → status do job
- `GET /analysis/{job_id}/result` → artefatos/JSON
- `POST /analysis/{job_id}/reproduce` → job reproduzido
- `POST /evidences/derivatives` → Evidence derivada
- `POST /cases/{id}/close` → CaseClosure iniciado
- `POST /cases/{id}/close/sign` → assinatura adicionada
- `POST /cases/{id}/reopen` → caso reaberto
- `GET /audit/verify-case-forensic/{case_id}` → relatório de integridade

## Restrições

- Caso fechado não deve permitir novas evidências/análises (validação pendente no código)
- Evidências duplicadas ativas rejeitadas no mesmo caso
- Tamanho máximo de upload: 500MB
- Apenas técnicas compatíveis com o tipo de mídia (validação parcial: `supported_types` exposto, mas não aplicado em `submit_job`)
- Usuário viewer não pode editar caso
- Apenas admin cria usuários

## Invariantes

- A cadeia de CustodyRecords é sequencial e encadeada por hash
- Todo registro de custódia possui assinatura Ed25519 válida
- O hash SHA-256 de um arquivo nunca muda após criação
- Caso fechado permanece imutável até reabertura (exceto pela ausência de validação que impede uploads/jobs)

## Erros de Domínio

- Caso fechado ou inexistente
- Permissão insuficiente
- Técnica não suportada para tipo de mídia
- Evidência duplicada
- Job não encontrado ou falho
- Cadeia de custódia quebrada
- Assinatura de fechamento pendente

## Evidências

- `src/backend/models/*.py`
- `src/backend/services/case_lifecycle_service.py`
- `src/backend/services/custody_service.py`
- `src/backend/services/evidence_service.py`
- `docs/specs/00-overview.md`
